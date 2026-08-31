#!/usr/bin/env python3
"""Platform kök sertifika depolarını üretir — ELLE çalıştırılır.

    cd backend && venv/bin/python tools/build_trust_stores.py

Bu script uygulama tarafından ASLA import edilmez. Ürettiği dosyalar
`backend/data/trust_stores/` altına yazılır ve depoya birlikte konur; çalışma
zamanında ağ erişimi yoktur, `ssl_chain_core` yalnızca bu dosyaları okur.

Neden gömülü veri?
------------------
"Bu zincir Android'de güvenilir mi?" sorusunun tek doğru cevabı Android'in
KENDİ kök deposuna karşı yol kurmaktır. Depolar birbirinden ciddi biçimde
ayrışıyor (Apple'da Mozilla'da olmayan ~25 kök, Android 7 ile güncel Android
arasında ~81 kök farkı), bu yüzden "certifi'ye bak, parmak izini diğer
listelerle kesiştir" kestirmesi yanlış sonuç üretir.

Kaynaklar
---------
* CCADB "Root CA Certificates Included by Root Stores" raporu — Apple, Google
  Chrome, Microsoft ve Mozilla köklerini PEM'i ve güven durumu sütunlarıyla
  birlikte tek CSV'de verir.
* AOSP `platform/system/ca-certificates` — Android sistem deposu. Dal başına
  bir tarball; `main` güncel Android, `nougat-release` Android 7 (eski cihaz
  vekili).

Not: CCADB bir Salesforce uç noktası ve hız sınırlaması uyguluyor. Script
yarım dosya BIRAKMAZ — her şey geçici dosyaya yazılır, hepsi başarılıysa
tek seferde yerine taşınır.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import os
import re
import sys
import tarfile
import urllib.request

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding

# ── Kaynaklar ─────────────────────────────────────────────────────────────────

CCADB_URL = (
    "https://ccadb.my.salesforce-sites.com/ccadb/"
    "RootCACertificatesIncludedByRSReportCSV"
)

AOSP_URL = (
    "https://android.googlesource.com/platform/system/ca-certificates/"
    "+archive/refs/heads/{branch}/files.tar.gz"
)

# CCADB durum sütunu -> ürettiğimiz depo adı
CCADB_STORES = {
    "apple": "Apple Status",
    "chrome": "Google Chrome Status",
    "microsoft": "Microsoft Status",
    "mozilla": "Mozilla Status",
}

# AOSP dalı -> depo adı
AOSP_STORES = {
    "android": "main",
    "android7": "nougat-release",
}

# Yalnızca TLS sunucu kimlik doğrulaması için güvenilen kökleri alıyoruz.
# CCADB aynı tabloda S/MIME ve kod imzalama köklerini de taşıyor; onları
# alırsak "güvenilir" dediğimiz kökler tarayıcıların TLS için kabul
# etmediklerini de kapsar ve rapor yalancı olur.
TLS_USE_CASE = "Server Authentication"

# Beklenen büyüklük mertebeleri. Gerçek sayı bunun altına düşerse kaynak
# bozulmuş ya da kısmi indirilmiş demektir — sessizce eksik depo yazmaktansa
# patlamak yeğdir.
MIN_ROOTS = 60

TIMEOUT = 120
USER_AGENT = "HostCheck-trust-store-builder/1.0"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "data", "trust_stores"))

_PEM_RE = re.compile(
    rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S
)


# ── Yardımcılar ───────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(msg, flush=True)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        if resp.status != 200:
            raise RuntimeError(f"{url} -> HTTP {resp.status}")
        return resp.read()


def _parse_pem_blocks(blob: bytes) -> list[x509.Certificate]:
    """PEM bloklarını TEK TEK ayrıştırır.

    `load_pem_x509_certificates()` ya hep ya hiç çalışıyor; kök setlerinde
    negatif serili (RFC 5280 ihlali) sertifikalar var ve bunlar cryptography'nin
    ileriki sürümlerinde istisna fırlatacak. Tek bir bozuk kök yüzünden bütün
    depoyu kaybetmeyelim.
    """
    out: list[x509.Certificate] = []
    for m in _PEM_RE.finditer(blob):
        try:
            out.append(x509.load_pem_x509_certificate(m.group(0)))
        except Exception as e:  # noqa: BLE001 — hangi sertifika olduğunu bilmiyoruz
            _log(f"    ! ayrıştırılamayan sertifika atlandı: {type(e).__name__}: {e}")
    return out


def _fingerprint(cert: x509.Certificate) -> str:
    return cert.fingerprint(hashes.SHA256()).hex()


def _dump_store(certs: list[x509.Certificate], title: str) -> str:
    """Sertifikaları SHA-256'ya göre SIRALI PEM metnine çevirir.

    Sıralama şart: kaynak CSV'nin satır sırası her indirmede değişebiliyor.
    Sıralamazsak depoyu her tazelediğimizde 150 satırlık anlamsız bir diff
    çıkar ve gerçek değişiklik (kök eklendi/çıkarıldı) gözden kaçar.
    """
    uniq: dict[str, x509.Certificate] = {}
    for c in certs:
        uniq.setdefault(_fingerprint(c), c)

    parts = [
        f"# HostCheck güven deposu — {title}\n",
        f"# {len(uniq)} kök, SHA-256 parmak izine göre sıralı.\n",
        "# tools/build_trust_stores.py tarafından üretildi — ELLE DÜZENLEMEYİN.\n",
    ]
    for fp in sorted(uniq):
        cert = uniq[fp]
        subject = cert.subject.rfc4514_string().replace("\n", " ")
        parts.append(f"\n# {subject}\n# SHA-256: {fp}\n")
        parts.append(cert.public_bytes(Encoding.PEM).decode("ascii"))
    return "".join(parts)


# ── Kaynak okuyucular ─────────────────────────────────────────────────────────

def build_ccadb_stores() -> dict[str, list[x509.Certificate]]:
    _log(f"CCADB indiriliyor: {CCADB_URL}")
    raw = _fetch(CCADB_URL)
    _log(f"  {len(raw):,} bayt")

    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    _log(f"  {len(rows)} kayıt")

    need = {"X.509 Certificate (PEM)", "Intended Use Case(s) Served"} | set(
        CCADB_STORES.values()
    )
    missing = need - set(rows[0].keys())
    if missing:
        raise RuntimeError(
            f"CCADB rapor biçimi değişmiş, eksik sütunlar: {sorted(missing)}"
        )

    stores: dict[str, list[x509.Certificate]] = {k: [] for k in CCADB_STORES}
    skipped_non_tls = 0

    for row in rows:
        if TLS_USE_CASE not in (row["Intended Use Case(s) Served"] or ""):
            skipped_non_tls += 1
            continue
        # CCADB PEM'i tek hücreye sığdırmak için tırnak içine alıyor.
        certs = _parse_pem_blocks(
            (row["X.509 Certificate (PEM)"] or "").replace("'", "").strip().encode()
        )
        if not certs:
            continue
        for name, column in CCADB_STORES.items():
            if (row[column] or "").strip() == "Included":
                stores[name].append(certs[0])

    _log(f"  TLS dışı {skipped_non_tls} kayıt atlandı")
    return stores


def build_aosp_store(branch: str) -> list[x509.Certificate]:
    url = AOSP_URL.format(branch=branch)
    _log(f"AOSP indiriliyor ({branch}): {url}")
    raw = _fetch(url)
    _log(f"  {len(raw):,} bayt")

    certs: list[x509.Certificate] = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            fh = tar.extractfile(member)
            if fh is None:
                continue
            # AOSP dosyaları PEM + insan okunur döküm içerir; PEM'i süzüyoruz.
            certs.extend(_parse_pem_blocks(fh.read()))
    return certs


# ── Ana akış ──────────────────────────────────────────────────────────────────

def main() -> int:
    stores: dict[str, list[x509.Certificate]] = {}

    try:
        stores.update(build_ccadb_stores())
        for name, branch in AOSP_STORES.items():
            stores[name] = build_aosp_store(branch)
    except Exception as e:  # noqa: BLE001
        _log(f"\nHATA: kaynak indirilemedi — {type(e).__name__}: {e}")
        _log("Hiçbir dosya yazılmadı; mevcut depolar olduğu gibi duruyor.")
        return 1

    _log("")
    for name, certs in sorted(stores.items()):
        uniq = len({_fingerprint(c) for c in certs})
        _log(f"  {name:<10} {uniq:>4} kök")
        if uniq < MIN_ROOTS:
            _log(
                f"\nHATA: '{name}' deposunda yalnızca {uniq} kök var "
                f"(beklenen en az {MIN_ROOTS}). Kaynak bozuk ya da kısmi "
                f"indirilmiş olabilir. Hiçbir dosya yazılmadı."
            )
            return 1

    titles = {
        "apple": "Apple (iOS / macOS)",
        "chrome": "Google Chrome Root Program",
        "microsoft": "Microsoft (Windows)",
        "mozilla": "Mozilla (Firefox)",
        "android": "Android sistem deposu — AOSP main",
        "android7": "Android 7 (Nougat) sistem deposu — eski cihaz vekili",
    }

    os.makedirs(OUT_DIR, exist_ok=True)

    # Önce hepsini ".yeni" olarak yaz, hepsi başarılıysa yerine taşı.
    written: list[tuple[str, str]] = []
    counts: dict[str, int] = {}
    for name, certs in stores.items():
        text = _dump_store(certs, titles[name])
        counts[name] = len({_fingerprint(c) for c in certs})
        tmp = os.path.join(OUT_DIR, f"{name}.pem.yeni")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        written.append((tmp, os.path.join(OUT_DIR, f"{name}.pem")))

    meta = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "counts": counts,
        "sources": {
            "ccadb": CCADB_URL,
            "aosp": {name: AOSP_URL.format(branch=b) for name, b in AOSP_STORES.items()},
        },
        "tls_use_case_filter": TLS_USE_CASE,
        "note": (
            "tools/build_trust_stores.py ile üretildi. Tazelemek için scripti "
            "yeniden çalıştırın; kökler SHA-256'ya göre sıralı yazıldığı için "
            "diff yalnızca gerçek değişikliği gösterir."
        ),
    }
    meta_tmp = os.path.join(OUT_DIR, "meta.json.yeni")
    with open(meta_tmp, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    written.append((meta_tmp, os.path.join(OUT_DIR, "meta.json")))

    for tmp, final in written:
        os.replace(tmp, final)

    _log(f"\n{len(written)} dosya yazıldı -> {OUT_DIR}")
    _log(f"Üretim zamanı: {meta['generated_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
