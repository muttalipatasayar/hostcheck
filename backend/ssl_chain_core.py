"""SSL sertifika zinciri doğrulama motoru — SSL Labs "Certification Paths" muadili.

Bu modülde FastAPI YOKTUR; uç nokta `routers/ssl_tools.py` içindedir
(`dns_core.py` / `mail_analysis.py` / `error_analysis.py` ile aynı desen).
Böylece motor FastAPI olmadan da import edilip denenebilir, ve `import OpenSSL`
koruması tek bir yerde durur.

Neden var
---------
Mevcut `/api/ssl/check`, doğrulamayı SORGUYU YAPAN MAKİNENİN işletim sistemi
güven deposuna göre yapıp tek bir boolean döndürüyor. Sahadaki asıl vaka bunu
yakalamaz: **site masaüstünde açılır, Android telefonda "güvenli değil" verir.**

Sebep neredeyse her zaman aynı — sunucu ara sertifikayı göndermiyor. Masaüstü
tarayıcılar eksik halkayı sertifikadaki AIA `caIssuers` adresinden kendileri
indirip onarır; **Android'in sistem TrustManager'ı AIA çekmez** ve bağlantıyı
keser. Paneli çalıştıran makine eksik halkayı zaten bildiği için mevcut araç
her iki durumda da "güvenilir" der.

Bu modülün çözümü: her güven deposuna karşı doğrulamayı İKİ KEZ çalıştırmak.

    A geçişi — yalnızca sunucunun gönderdiği sertifikalar
               → Android sistem (WebView, OkHttp, native) ne görüyorsa o
    B geçişi — sunucununkiler + özyinelemeli AIA ile indirilenler
               → iOS/Safari, Chrome, Edge, Windows ne görüyorsa o

A ❌ + B ✅  ⇒  "masaüstünde çalışıyor, Android'de kırık".

İki bağımsız kehanet
--------------------
1. `cryptography.x509.verification` → "public WebPKI profiline uyuyor mu?"
2. `_build_own_path()` → "kriptografik olarak zincir kuruluyor mu?"

(2) geçip (1) kalıyorsa — cPanel/Plesk self-signed ve iç CA sertifikalarının
tipik hâli — bu aracın üretebileceği en değerli çıktı odur. Tek kehanetle
çalışsaydık bu sertifikalar sebepsizce "hiçbir platformda güvenilmiyor"
görünürdü.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import json
import os
import re
import select
import socket
import time
import urllib.parse
import warnings
from dataclasses import dataclass, field
from typing import Optional

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, rsa
from cryptography.hazmat.primitives.serialization import Encoding, pkcs7
from cryptography.x509.oid import (
    AuthorityInformationAccessOID,
    ExtendedKeyUsageOID,
    ExtensionOID,
    NameOID,
)
from cryptography.x509.verification import (
    Criticality,
    DNSName,
    ExtensionPolicy,
    PolicyBuilder,
    Store,
    VerificationError,
)

# CCADB ve AOSP kök setlerinde RFC 5280'i ihlal eden (negatif/sıfır serili)
# sertifikalar var. Bugün uyarı, ileride istisna olacaklar.
#
# `warnings.catch_warnings()` KULLANILMIYOR: süreç-global durumu değiştirir ve
# paylaşılan thread havuzunda diğer isteklerle yarışır. Modül seviyesinde bir
# kez süzmek doğru olan.
try:  # pragma: no cover
    from cryptography.utils import CryptographyDeprecationWarning

    warnings.filterwarnings(
        "ignore", category=CryptographyDeprecationWarning, message=".*serial number.*"
    )
    # Bazı köklerin RDN'i 64 karakteri aşıyor; cryptography uyarıyor ama
    # sertifikayı yükleyebiliyor. Kök depolarını her yüklediğimizde bu uyarıyı
    # tekrar basmanın anlamı yok.
    warnings.filterwarnings("ignore", category=UserWarning, message=".*Attribute's length.*")
except Exception:  # pragma: no cover
    pass

# `import OpenSSL` KORUMALI OLMAK ZORUNDA.
#
# main.py router'ları import zamanında yüklüyor. Paket kurulu değilse uvicorn
# hiç açılmaz; systemd'deki `Restart=always` + `RestartSec=3` bunu DNS, SSH,
# RDP, FTP dahil BÜTÜN panelin kalıcı kesintisine çevirir. Desen
# `quick_check.py`'deki DNS_AVAILABLE ile aynı.
try:
    from OpenSSL import SSL as _ossl

    CHAIN_AVAILABLE = True
    CHAIN_UNAVAILABLE_REASON = ""
except Exception as _e:  # pragma: no cover
    _ossl = None
    CHAIN_AVAILABLE = False
    CHAIN_UNAVAILABLE_REASON = (
        f"pyOpenSSL yüklenemedi ({type(_e).__name__}). "
        "Kurulum: pip install -r requirements.txt"
    )

# net_validation SSRF kapısı. HTTPException fırlatır; motor içinde onu
# yakalayıp "genel değil" olarak yorumluyoruz (bkz. _resolve_public_or_none).
from net_validation import resolve_public_ips_async  # noqa: E402


# ── Sabitler ──────────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))
TRUST_STORE_DIR = os.path.join(_HERE, "data", "trust_stores")

STORE_NAMES = ("apple", "chrome", "microsoft", "mozilla", "android", "android7")

HANDSHAKE_TIMEOUT = 10.0

# TLS el sıkışmaları için AYRILMIŞ havuz.
#
# `run_in_executor(None, ...)` KULLANILMAZ: varsayılan havuzu
# `resolve_public_ips_async`, whois ve dnspython paylaşıyor. Bir el sıkışma
# 10 sn'ye kadar bir thread tutar; havuz dolduğunda ALÂKASIZ araçlar
# "Alan adı çözümlemesi zaman aşımına uğradı" vermeye başlar.
#
# Hem `/api/ssl/chain-check` hem Hızlı Kontrol'ün SSL teşhisi buradan geçer;
# ikisinin toplam eşzamanlılığı bu havuzla sınırlıdır.
CHAIN_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="ssl-chain")

# Sunucunun gönderdiği zinciri bu sayıda sertifikada kırpıyoruz. İmza
# doğrulaması çiftler üzerinde O(n²); OpenSSL'in 100 KB'lik max_cert_list
# sınırı zaten üst sınır koyuyor, bu ikinci emniyet.
MAX_CHAIN_CERTS = 12

# AIA bütçesi. ÇEKİM BAŞINA değil TOPLAM — 4 × 5 sn = 20 sn kabul edilemez.
AIA_MAX_FETCHES = 4
AIA_TOTAL_BUDGET = 6.0
AIA_MAX_BYTES = 100 * 1024
AIA_CONNECT_TIMEOUT = 3.0
AIA_READ_TIMEOUT = 3.0

_PEM_RE = re.compile(
    rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S
)

# CA/Browser Forum SC-081v3 — azalan azami geçerlilik takvimi.
#
# 398 gün ARTIK GEÇERLİ DEĞİL. Sınır sertifikanın notBefore'una göre belirlenir,
# "bugüne" göre değil. Sabit 398 yazmak, Apple ve Chrome'un bugün reddettiği
# sertifikaları sessizce geçirir.
_VALIDITY_SCHEDULE = (
    (datetime.date(2029, 3, 15), 47),
    (datetime.date(2027, 3, 15), 100),
    (datetime.date(2026, 3, 15), 200),
    (datetime.date(2020, 9, 1), 398),
)
_VALIDITY_LEGACY_LIMIT = 825


# ── Veri tipleri ──────────────────────────────────────────────────────────────

@dataclass
class Finding:
    """Tek bir bulgu. `status` projenin dört durumlu sözlüğü.

    `oncelik` yalnızca ÖZET cümlesi seçilirken kullanılır (küçük = önemli).
    Listeleme sırası bundan etkilenmez; teknisyen bulguları oluşum sırasında
    görür. Önceliksiz bırakılırsa hepsi eşit sayılır ve ilk hata öne çıkar —
    bu da "kökü güvenilmiyor" yerine "geçerlilik süresi uzun" gibi ikincil bir
    cümleyi başlığa taşıyabilir.
    """

    label: str
    status: str  # healthy | warning | error | info
    detail: str = ""
    fix: str = ""
    oncelik: int = 50


@dataclass
class CertInfo:
    position: int
    role: str  # yaprak | ara | kök
    subject: str
    issuer: str
    common_name: str
    organization: str
    serial: str
    not_before: str
    not_after: str
    days_remaining: int
    expired: bool
    not_yet_valid: bool
    signature_algorithm: str
    key_algorithm: str
    key_size: Optional[int]
    is_ca: bool
    self_signed: bool
    sha256: str
    san: list[str] = field(default_factory=list)
    source: str = "sunucu"  # sunucu | AIA
    aia_ca_issuers: list[str] = field(default_factory=list)
    ocsp_urls: list[str] = field(default_factory=list)
    sct_count: int = 0
    key_usage: list[str] = field(default_factory=list)
    ext_key_usage: list[str] = field(default_factory=list)


@dataclass
class HandshakeResult:
    certs: list[x509.Certificate]
    protocol: str = ""
    cipher: str = ""
    ocsp_stapled: bool = False
    parse_errors: list[str] = field(default_factory=list)
    truncated: bool = False
    leaf_mismatch: bool = False


# ── Güven depoları ────────────────────────────────────────────────────────────

_store_cache: dict[str, tuple[Store, list[x509.Certificate], int]] = {}
_meta_cache: Optional[dict] = None
_store_errors: dict[str, str] = {}


def _parse_pem_blocks(blob: bytes) -> tuple[list[x509.Certificate], int]:
    """PEM bloklarını TEK TEK ayrıştırır; (sertifikalar, bozuk_sayısı) döner.

    `load_pem_x509_certificates()` ya hep ya hiç çalışıyor. Kök setlerinde
    RFC ihlali sertifikalar var; tek bir bozuk kök yüzünden koca bir platformun
    deposunu kaybetmek, o platform için sessizce yanlış cevap vermek demektir.
    """
    certs: list[x509.Certificate] = []
    bad = 0
    for m in _PEM_RE.finditer(blob):
        try:
            certs.append(x509.load_pem_x509_certificate(m.group(0)))
        except Exception:  # noqa: BLE001
            bad += 1
    return certs, bad


def load_store_meta() -> dict:
    global _meta_cache
    if _meta_cache is None:
        try:
            with open(os.path.join(TRUST_STORE_DIR, "meta.json"), encoding="utf-8") as fh:
                _meta_cache = json.load(fh)
        except Exception:  # noqa: BLE001
            _meta_cache = {}
    return _meta_cache


def get_store(name: str) -> Optional[tuple[Store, list[x509.Certificate], int]]:
    """Bir platform deposunu yükler (tembel + önbellekli).

    ÖNBELLEĞE ALINAN `Store`'dur, `ServerVerifier` DEĞİL: doğrulayıcı
    `build_server_verifier()` çağrıldığı anda geçerlilik zamanını dondurur.
    Süreç haftalarca ayakta kalabildiği için dondurulmuş bir saat, süresi
    dolmuş sertifikaları geçerli göstermeye başlardı.
    """
    if name in _store_cache:
        return _store_cache[name]
    if name in _store_errors:
        return None

    path = os.path.join(TRUST_STORE_DIR, f"{name}.pem")
    try:
        with open(path, "rb") as fh:
            certs, bad = _parse_pem_blocks(fh.read())
    except FileNotFoundError:
        _store_errors[name] = (
            f"Güven deposu dosyası yok: data/trust_stores/{name}.pem — "
            "backend/tools/build_trust_stores.py çalıştırılmalı"
        )
        return None
    except Exception as e:  # noqa: BLE001
        _store_errors[name] = f"Güven deposu okunamadı ({name}): {type(e).__name__}"
        return None

    if not certs:
        _store_errors[name] = f"Güven deposu boş: {name}.pem"
        return None

    entry = (Store(certs), certs, bad)
    _store_cache[name] = entry
    return entry


# Kök depoları yavaş değişir ama sonsuza kadar geçerli değildir: CA'lar
# eklenir, güvenden düşürülenler çıkarılır (E-Tugra 2023-24 gibi). Gömülü
# veri bayatladığında araç SESSİZCE yanlış cevap vermeye başlar — "bu kök
# Android'de yok" derken aslında eklenmiş olabilir. Bu yüzden bayatlık
# görünür bir bulgu olarak raporlanır.
STORE_STALE_DAYS = 180


def store_health_findings() -> list[Finding]:
    """Depoların sağlığını bulgu olarak raporlar (500 yerine görünür uyarı)."""
    out: list[Finding] = []
    meta = load_store_meta()
    expected = meta.get("counts", {})

    uretim = meta.get("generated_at", "")
    if uretim:
        try:
            t = datetime.datetime.fromisoformat(uretim)
            if t.tzinfo is None:
                t = t.replace(tzinfo=datetime.timezone.utc)
            yas = (datetime.datetime.now(datetime.timezone.utc) - t).days
            if yas > STORE_STALE_DAYS:
                out.append(Finding(
                    label="Kök depoları bayatlamış",
                    status="warning",
                    oncelik=40,
                    detail=(
                        f"Gömülü kök sertifika depoları {yas} gün önce üretilmiş. "
                        "Bu süreçte CA eklenmiş ya da güvenden düşürülmüş olabilir; "
                        "platform sonuçları yanıltıcı olabilir."
                    ),
                    fix="backend/tools/build_trust_stores.py çalıştırıp dosyaları yayına kopyalayın.",
                ))
        except Exception:  # noqa: BLE001 — bozuk tarih bulgu üretmesin
            pass

    for name in STORE_NAMES:
        entry = get_store(name)
        if entry is None:
            out.append(
                Finding(
                    label=f"Güven deposu: {name}",
                    status="error",
                    detail=_store_errors.get(name, "yüklenemedi"),
                    fix="backend/tools/build_trust_stores.py çalıştırıp dosyaları yayına kopyalayın.",
                )
            )
            continue
        _, certs, bad = entry
        want = expected.get(name)
        if bad or (want is not None and len(certs) != want):
            out.append(
                Finding(
                    label=f"Güven deposu: {name}",
                    status="info",
                    detail=(
                        f"{len(certs)} kök yüklendi"
                        + (f", beklenen {want}" if want is not None else "")
                        + (f", {bad} sertifika ayrıştırılamadı" if bad else "")
                    ),
                )
            )
    return out


def _all_anchor_subjects() -> set:
    subjects = set()
    for name in STORE_NAMES:
        entry = get_store(name)
        if entry:
            for c in entry[1]:
                subjects.add(c.subject)
    return subjects


# ── TLS el sıkışması ──────────────────────────────────────────────────────────

def _with_tls_retry(fn, sock, deadline):
    """WantRead/WantWrite döngüsü.

    `sock.settimeout()` Python'da soketi non-blocking yapıyor; pyOpenSSL bunu
    görünce `SSL_ERROR_WANT_READ` fırlatıyor. Doğru desen, select ile bekleyip
    tekrar denemek. Zaman aşımını burada kendimiz uyguluyoruz çünkü dış
    `asyncio.wait_for` executor'da BAŞLAMIŞ işi iptal edemez.
    """
    while True:
        try:
            return fn()
        except _ossl.WantReadError:
            kalan = deadline - time.monotonic()
            if kalan <= 0 or not select.select([sock], [], [], kalan)[0]:
                raise socket.timeout("TLS el sıkışma zaman aşımı")
        except _ossl.WantWriteError:
            kalan = deadline - time.monotonic()
            if kalan <= 0 or not select.select([], [sock], [], kalan)[1]:
                raise socket.timeout("TLS el sıkışma zaman aşımı")


def _make_context():
    ctx = _ossl.Context(_ossl.TLS_CLIENT_METHOD)

    # Doğrulamayı KENDİMİZ yapıyoruz. VERIFY_NONE olmasaydı bozuk zincirli bir
    # sunucudan hiçbir veri alamaz, "el sıkışma hatası" deyip teşhis edilecek
    # asıl sorunu kaçırırdık.
    ctx.set_verify(_ossl.VERIFY_NONE, lambda *a: True)

    # OpenSSL 3.0 varsayılanları, teşhis etmemiz gereken tam da o eski
    # sunucularla (TLS 1.0, 3DES, RSA-1024) el sıkışmayı reddediyor. Hosting
    # destek paneli için bu yanlış başarısızlık: müşteri "siteme girilmiyor"
    # diyor, araç "el sıkışma hatası" deyip susuyor.
    try:
        ctx.set_min_proto_version(_ossl.TLS1_VERSION)
    except Exception:  # noqa: BLE001
        pass
    try:
        ctx.set_cipher_list(b"ALL:@SECLEVEL=0")
    except Exception:  # noqa: BLE001
        pass
    return ctx


def fetch_chain_sync(
    host: str, ip: str, port: int, use_sni: bool = True
) -> HandshakeResult:
    """Sunucunun GERÇEKTEN gönderdiği zinciri, GÖNDERDİĞİ SIRAYLA alır.

    Python 3.12'de stdlib `ssl` yalnızca yaprağı verebiliyor
    (`get_unverified_chain()` 3.13+). Ara sertifikaları görmeden zincir
    teşhisi yapılamaz, bu yüzden pyOpenSSL şart.

    `ip` doğrulanmış hedeftir; bağlantı ORAYA kurulur, isim yeniden
    çözümlenmez (DNS rebinding penceresi kapalı). SNI ve hostname eşleşmesi
    yine alan adına göre yapılır.
    """
    result = HandshakeResult(certs=[])
    stapled: dict[str, bool] = {"ok": False}

    def _ocsp_cb(conn, ocsp_bytes, data):
        if ocsp_bytes:
            stapled["ok"] = True
        return True

    ctx = _make_context()
    try:
        ctx.set_ocsp_client_callback(_ocsp_cb)
    except Exception:  # noqa: BLE001
        pass

    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    # asyncio.wait_for executor'da BAŞLAMIŞ işi iptal edemez; dış zaman aşımı
    # yalnızca tavsiyedir. Gerçek koruma soketin kendi timeout'u.
    sock.settimeout(HANDSHAKE_TIMEOUT)
    deadline = time.monotonic() + HANDSHAKE_TIMEOUT

    conn = None
    try:
        sock.connect((ip, port))
        conn = _ossl.Connection(ctx, sock)
        if use_sni:
            conn.set_tlsext_host_name(host.encode("idna") if not host.isascii() else host.encode())
        try:
            conn.request_ocsp()
        except Exception:  # noqa: BLE001
            pass
        conn.set_connect_state()
        _with_tls_retry(conn.do_handshake, sock, deadline)

        try:
            result.protocol = conn.get_protocol_version_name() or ""
            cipher = conn.get_cipher_name()
            result.cipher = cipher or ""
        except Exception:  # noqa: BLE001
            pass

        chain = conn.get_peer_cert_chain(as_cryptography=True)
        leaf = conn.get_peer_certificate(as_cryptography=True)

        # get_peer_cert_chain() oturum devamında ya da sunucu Certificate
        # mesajı hiç göndermediğinde None dönebilir.
        certs = list(chain) if chain else []
        if not certs and leaf is not None:
            certs = [leaf]
        elif certs and leaf is not None:
            if certs[0].fingerprint(hashes.SHA256()) != leaf.fingerprint(hashes.SHA256()):
                # Zincirin başı yaprak değil — get_peer_certificate() otorite.
                result.leaf_mismatch = True
                certs = [leaf] + [
                    c for c in certs
                    if c.fingerprint(hashes.SHA256()) != leaf.fingerprint(hashes.SHA256())
                ]

        if len(certs) > MAX_CHAIN_CERTS:
            result.truncated = True
            certs = certs[:MAX_CHAIN_CERTS]

        result.certs = certs
        result.ocsp_stapled = stapled["ok"]
    finally:
        if conn is not None:
            try:
                conn.shutdown()
            except Exception:  # noqa: BLE001
                pass
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            sock.close()
        except Exception:  # noqa: BLE001
            pass

    return result


def handshake_error_message(e: BaseException, host: str, port: int) -> str:
    """El sıkışma istisnasını teknisyenin okuyacağı Türkçeye çevirir."""
    if isinstance(e, (socket.timeout, TimeoutError)):
        return f"Bağlantı zaman aşımı — {host}:{port} yanıt vermiyor"
    if isinstance(e, ConnectionRefusedError):
        return f"Bağlantı reddedildi — {host}:{port} kapalı olabilir"
    if _ossl is not None and isinstance(e, _ossl.Error):
        text = ""
        try:
            args = e.args[0]
            if args:
                text = str(args[0][-1])
        except Exception:  # noqa: BLE001
            text = str(e)[:120]
        low = text.lower()
        if "excessive message size" in low or "too long" in low:
            return (
                "Sunucunun gönderdiği sertifika zinciri 100 KB'yi aşıyor ve "
                "OpenSSL bu boyutta bir zinciri kabul etmiyor. Zincire alakasız "
                "sertifikalar eklenmiş ya da sertifikada çok sayıda alan adı (SAN) "
                "olabilir. Bu boyut birçok istemcide de sorun çıkarır."
            )
        if "unsupported protocol" in low or "protocol version" in low:
            return (
                "TLS sürümü uyuşmuyor — sunucu yalnızca bu istemcinin "
                "desteklemediği eski bir sürüm konuşuyor olabilir"
            )
        if "handshake failure" in low or "no cipher" in low or "sslv3 alert" in low:
            return (
                f"TLS el sıkışması reddedildi ({text or 'handshake failure'}) — "
                "sunucu çok eski bir şifre süiti kullanıyor ya da bu portta TLS konuşmuyor"
            )
        if "wrong version number" in low or "packet length" in low:
            return f"Port {port} TLS konuşmuyor — düz metin servis olabilir"
        return f"TLS hatası: {text or str(e)[:120]}"
    if isinstance(e, OSError):
        return f"Bağlantı hatası: {e}"
    return f"Beklenmeyen hata: {type(e).__name__}: {str(e)[:120]}"


# ── AIA onarımı ───────────────────────────────────────────────────────────────
#
# DİKKAT: buradaki URL SERTİFİKANIN İÇİNDEN geliyor, yani hedef alan adının
# sahibi belirliyor. `/api/ssl/` nginx'te auth'suz ve internete açık blokta
# olduğu için bu, kimliksiz bir "dışarı GET at" primitifidir. Kısıtlar:
#
#   • yalnız http:// ve yalnız port 80 (CABF BR'leri zaten http şart koşuyor)
#   • kimlik bilgisi gömülü URL reddedilir
#   • host net_validation kapısından geçer, bağlantı DOĞRULANMIŞ IP'ye kurulur
#   • yönlendirme takip edilmez
#   • TOPLAM 6 sn bütçe (çekim başına değil), en fazla 4 çekim
#   • gövde akışla okunur, 100 KB'de kesilir (resp.content gövdeyi tamponlar)
#   • hem URL hem sertifika parmak izi ile tekilleştirme
#   • YANIT GÖVDESİ ASLA YANKILANMAZ — çıktıya yalnızca X.509 olarak
#     ayrıştırılabilmiş baytlar girer

async def _resolve_public_or_none(host: str) -> Optional[list[str]]:
    """Host genel bir adrese çözümleniyorsa IP listesi, değilse None.

    GÜVENLİK — event loop'u bloklamamak ZORUNDA.

    Bu fonksiyon `_fetch_aia_once` içinden, yani event loop üzerinde çağrılıyor.
    Eskiden senkron `resolve_public_ips` çağırıyordu ve o da zaman aşımı
    OLMAYAN `socket.getaddrinfo`'ya iniyordu.

    Buradaki host SERTİFİKANIN AIA alanından geliyor: hedef alan adının sahibi
    onu belirler, YANİ NAMESERVER'I DA SALDIRGANIN. Yanıt vermeyen bir
    nameserver ile tek bir istek, tek worker'lı panelin event loop'unu
    işletim sisteminin resolver zaman aşımı boyunca (resolv.conf'a göre
    onlarca saniye) tamamen dondurabiliyordu — kimlik doğrulaması olmayan bir
    uçtan tam servis kesintisi.

    `resolve_public_ips_async` çözümlemeyi executor'a alır ve 5 sn'lik
    `asyncio.wait_for` ile sınırlar.
    """
    try:
        ips = await resolve_public_ips_async(host, 80)
    except Exception:  # noqa: BLE001 — HTTPException dahil her şey "genel değil"
        return None
    return ips or None


def _parse_aia_payload(raw: bytes) -> list[x509.Certificate]:
    """AIA yanıtını ayrıştırır: DER → PEM → PKCS#7-DER → PKCS#7-PEM.

    Birçok CA (DigiCert, Sectigo, Microsoft profilleri) caIssuers'ı ham DER
    değil PKCS#7 olarak sunuyor. Yalnız DER denenirse onarım sessizce
    başarısız olur ve kullanıcıya yanlışlıkla "zincir onarılamıyor" denir.
    """
    try:
        return [x509.load_der_x509_certificate(raw)]
    except Exception:  # noqa: BLE001
        pass
    certs, _ = _parse_pem_blocks(raw)
    if certs:
        return certs
    try:
        return list(pkcs7.load_der_pkcs7_certificates(raw))
    except Exception:  # noqa: BLE001
        pass
    try:
        return list(pkcs7.load_pem_pkcs7_certificates(raw))
    except Exception:  # noqa: BLE001
        pass
    return []


def ca_issuer_urls(cert: x509.Certificate) -> list[str]:
    try:
        aia = cert.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_INFORMATION_ACCESS
        ).value
    except x509.ExtensionNotFound:
        return []
    except Exception:  # noqa: BLE001
        return []
    out = []
    for desc in aia:
        if desc.access_method == AuthorityInformationAccessOID.CA_ISSUERS:
            try:
                out.append(str(desc.access_location.value))
            except Exception:  # noqa: BLE001
                continue
    return out


def ocsp_urls(cert: x509.Certificate) -> list[str]:
    try:
        aia = cert.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_INFORMATION_ACCESS
        ).value
    except Exception:  # noqa: BLE001
        return []
    out = []
    for desc in aia:
        if desc.access_method == AuthorityInformationAccessOID.OCSP:
            try:
                out.append(str(desc.access_location.value))
            except Exception:  # noqa: BLE001
                continue
    return out


async def repair_chain_via_aia(
    leaf: x509.Certificate,
    sent: list[x509.Certificate],
    loop_time,
) -> tuple[list[x509.Certificate], list[Finding]]:
    """Eksik ara sertifikaları AIA'dan ÖZYİNELEMELİ olarak indirir.

    Özyineleme şart: Let's Encrypt bugün `yaprak → YR2 → Root YR` kuruyor ve
    `Root YR` hiçbir kök deposunda yok — güven ISRG Root X1 çapraz imzasından
    geliyor. Tek AIA sıçraması bu zinciri onaramaz, iki sıçrama gerekir.
    """
    anchors = _all_anchor_subjects()
    pool = list(sent)
    fetched: list[x509.Certificate] = []
    findings: list[Finding] = []
    seen_urls: set[str] = set()
    seen_fps: set[bytes] = {c.fingerprint(hashes.SHA256()) for c in sent}

    deadline = loop_time() + AIA_TOTAL_BUDGET
    cur = leaf

    timeout = httpx.Timeout(
        connect=AIA_CONNECT_TIMEOUT, read=AIA_READ_TIMEOUT,
        write=AIA_READ_TIMEOUT, pool=AIA_CONNECT_TIMEOUT,
    )

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, verify=False
    ) as client:
        for _ in range(AIA_MAX_FETCHES):
            if cur.subject == cur.issuer or cur.issuer in anchors:
                break  # köke ya da bilinen bir çıpaya vardık

            nxt = next((c for c in pool if c.subject == cur.issuer and c is not cur), None)
            if nxt is not None:
                cur = nxt
                continue

            urls = [u for u in ca_issuer_urls(cur) if u not in seen_urls]
            if not urls:
                if not ca_issuer_urls(cur):
                    findings.append(
                        Finding(
                            label="AIA adresi yok",
                            status="warning",
                            detail=(
                                f"'{_short_name(cur)}' sertifikasında AIA caIssuers "
                                "alanı yok — hiçbir istemci eksik halkayı kendi başına indiremez."
                            ),
                            fix="Tek çözüm sunucudaki sertifika bundle'ını tamamlamak.",
                        )
                    )
                break

            url = urls[0]
            seen_urls.add(url)

            if loop_time() > deadline:
                findings.append(
                    Finding(
                        label="AIA süre bütçesi doldu",
                        status="warning",
                        detail=f"Ara sertifika indirme {AIA_TOTAL_BUDGET:.0f} sn içinde tamamlanamadı.",
                    )
                )
                break

            got, err = await _fetch_aia_once(client, url, deadline, loop_time)
            if err:
                findings.append(err)
                break
            if not got:
                break

            new = [c for c in got if c.fingerprint(hashes.SHA256()) not in seen_fps]
            if not new:
                break
            for c in new:
                seen_fps.add(c.fingerprint(hashes.SHA256()))
            fetched.extend(new)
            pool.extend(new)

            step = next((c for c in new if c.subject == cur.issuer), None)
            if step is None:
                break
            cur = step

    return fetched, findings


async def _fetch_aia_once(
    client: httpx.AsyncClient, url: str, deadline: float, loop_time
) -> tuple[list[x509.Certificate], Optional[Finding]]:
    parsed = urllib.parse.urlsplit(url)

    if parsed.scheme != "http":
        return [], Finding(
            label="AIA adresi atlandı",
            status="info",
            detail=f"Yalnızca http:// destekleniyor, gelen şema: {parsed.scheme or 'yok'}",
        )
    if parsed.username or parsed.password:
        return [], Finding(
            label="AIA adresi reddedildi",
            status="warning",
            detail="Adreste gömülü kimlik bilgisi var — güvenlik gereği indirilmedi.",
        )
    if parsed.port not in (None, 80):
        return [], Finding(
            label="AIA adresi reddedildi",
            status="warning",
            detail=f"Yalnızca port 80 destekleniyor, istenen port: {parsed.port}",
        )

    host = parsed.hostname or ""
    if not host:
        return [], Finding(label="AIA adresi geçersiz", status="warning", detail="Host bulunamadı.")

    ips = await _resolve_public_or_none(host)
    if not ips:
        # Bu tam olarak SSRF denemesinin görüneceği yer. Yanıt gövdesi bir yana,
        # hedefe BAĞLANMIYORUZ bile.
        return [], Finding(
            label="AIA hedefi genel adres değil",
            status="warning",
            detail=(
                f"Sertifikadaki AIA adresi ({host}) özel/yerel bir adrese "
                "çözümleniyor ya da çözümlenemiyor — indirilmedi."
            ),
        )

    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    for ip in ips:
        if loop_time() > deadline:
            break
        literal = f"[{ip}]" if ":" in ip else ip
        try:
            async with client.stream(
                "GET", f"http://{literal}{path}", headers={"Host": host}
            ) as resp:
                if resp.status_code != 200:
                    continue
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > AIA_MAX_BYTES:
                        return [], Finding(
                            label="AIA yanıtı çok büyük",
                            status="warning",
                            detail=f"{host} adresinden gelen yanıt {AIA_MAX_BYTES // 1024} KB sınırını aştı.",
                        )
                certs = _parse_aia_payload(bytes(buf))
                if certs:
                    return certs, None
        except Exception:  # noqa: BLE001 — upstream hata metni ASLA yankılanmaz
            continue

    return [], Finding(
        label="Ara sertifika indirilemedi",
        status="warning",
        detail=f"AIA adresinden ({host}) geçerli bir sertifika alınamadı.",
    )


# ── Sertifika yardımcıları ────────────────────────────────────────────────────

def _attr(name: x509.Name, oid) -> str:
    try:
        vals = name.get_attributes_for_oid(oid)
        return str(vals[0].value) if vals else ""
    except Exception:  # noqa: BLE001
        return ""


def _short_name(cert: x509.Certificate) -> str:
    cn = _attr(cert.subject, NameOID.COMMON_NAME)
    if cn:
        return cn
    org = _attr(cert.subject, NameOID.ORGANIZATION_NAME)
    if org:
        return org
    # CN'siz sertifikalar var (badssl'in no-subject testi gibi); boş etiket
    # basmaktansa SAN'ın ilk adına düşüyoruz.
    san = _san_dns(cert)
    if san:
        return san[0]
    dn = cert.subject.rfc4514_string()[:60]
    return dn or "(adsız sertifika)"


def _fp(cert: x509.Certificate) -> str:
    return cert.fingerprint(hashes.SHA256()).hex()


def _not_before(cert: x509.Certificate) -> datetime.datetime:
    return getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before.replace(
        tzinfo=datetime.timezone.utc
    )


def _not_after(cert: x509.Certificate) -> datetime.datetime:
    return getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(
        tzinfo=datetime.timezone.utc
    )


def _is_ca(cert: x509.Certificate) -> bool:
    try:
        return bool(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
    except Exception:  # noqa: BLE001
        return False


def _san_dns(cert: x509.Certificate) -> list[str]:
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = list(ext.get_values_for_type(x509.DNSName))
        try:
            names += [str(i) for i in ext.get_values_for_type(x509.IPAddress)]
        except Exception:  # noqa: BLE001
            pass
        return names
    except Exception:  # noqa: BLE001
        return []


def _key_info(cert: x509.Certificate) -> tuple[str, Optional[int]]:
    try:
        pub = cert.public_key()
    except Exception:  # noqa: BLE001
        return "bilinmiyor", None
    if isinstance(pub, rsa.RSAPublicKey):
        return "RSA", pub.key_size
    if isinstance(pub, ec.EllipticCurvePublicKey):
        return f"EC ({pub.curve.name})", pub.key_size
    if isinstance(pub, ed25519.Ed25519PublicKey):
        return "Ed25519", 256
    if isinstance(pub, ed448.Ed448PublicKey):
        return "Ed448", 448
    if isinstance(pub, dsa.DSAPublicKey):
        return "DSA", pub.key_size
    return type(pub).__name__, None


def _sig_alg(cert: x509.Certificate) -> str:
    try:
        h = cert.signature_hash_algorithm
        if h is None:
            return "Ed25519/Ed448"
        return h.name.upper()
    except Exception:  # noqa: BLE001
        return "bilinmiyor"


def _sct_count(cert: x509.Certificate) -> int:
    try:
        ext = cert.extensions.get_extension_for_oid(
            ExtensionOID.PRECERT_SIGNED_CERTIFICATE_TIMESTAMPS
        ).value
        return len(list(ext))
    except Exception:  # noqa: BLE001
        return 0


def _key_usage(cert: x509.Certificate) -> list[str]:
    try:
        ku = cert.extensions.get_extension_for_class(x509.KeyUsage).value
    except Exception:  # noqa: BLE001
        return []
    out = []
    for attr, label in (
        ("digital_signature", "digitalSignature"),
        ("content_commitment", "contentCommitment"),
        ("key_encipherment", "keyEncipherment"),
        ("data_encipherment", "dataEncipherment"),
        ("key_agreement", "keyAgreement"),
        ("key_cert_sign", "keyCertSign"),
        ("crl_sign", "cRLSign"),
    ):
        try:
            if getattr(ku, attr):
                out.append(label)
        except Exception:  # noqa: BLE001
            continue
    return out


def _ext_key_usage(cert: x509.Certificate) -> list[str]:
    try:
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    except Exception:  # noqa: BLE001
        return []
    friendly = {
        ExtendedKeyUsageOID.SERVER_AUTH.dotted_string: "serverAuth",
        ExtendedKeyUsageOID.CLIENT_AUTH.dotted_string: "clientAuth",
        ExtendedKeyUsageOID.CODE_SIGNING.dotted_string: "codeSigning",
        ExtendedKeyUsageOID.EMAIL_PROTECTION.dotted_string: "emailProtection",
        ExtendedKeyUsageOID.TIME_STAMPING.dotted_string: "timeStamping",
        ExtendedKeyUsageOID.OCSP_SIGNING.dotted_string: "OCSPSigning",
    }
    return [friendly.get(o.dotted_string, o.dotted_string) for o in eku]


def _host_matches(pattern: str, host: str) -> bool:
    """RFC 6125 hostname eşleşmesi — joker YALNIZCA en soldaki etiketi karşılar."""
    pattern = (pattern or "").lower().rstrip(".")
    host = (host or "").lower().rstrip(".")
    if not pattern or not host:
        return False
    if pattern == host:
        return True
    if pattern.startswith("*."):
        suffix = pattern[2:]
        if not suffix or "." not in suffix:
            return False  # *.com gibi bir joker kabul edilmez
        if host.endswith("." + suffix):
            left = host[: -(len(suffix) + 1)]
            return bool(left) and "." not in left
    return False


def _validity_limit_days(not_before: datetime.datetime) -> int:
    """SC-081v3 takvimine göre bu sertifikaya uygulanan azami geçerlilik."""
    d = not_before.date()
    for threshold, limit in _VALIDITY_SCHEDULE:
        if d >= threshold:
            return limit
    return _VALIDITY_LEGACY_LIMIT


def cert_info(cert: x509.Certificate, position: int, role: str, source: str, now) -> CertInfo:
    nb, na = _not_before(cert), _not_after(cert)
    algo, size = _key_info(cert)
    return CertInfo(
        position=position,
        role=role,
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        common_name=_attr(cert.subject, NameOID.COMMON_NAME),
        organization=_attr(cert.subject, NameOID.ORGANIZATION_NAME),
        serial=format(cert.serial_number, "x"),
        not_before=nb.strftime("%d.%m.%Y %H:%M UTC"),
        not_after=na.strftime("%d.%m.%Y %H:%M UTC"),
        days_remaining=(na - now).days,
        expired=na < now,
        not_yet_valid=nb > now,
        signature_algorithm=_sig_alg(cert),
        key_algorithm=algo,
        key_size=size,
        is_ca=_is_ca(cert),
        self_signed=cert.subject == cert.issuer,
        sha256=_fp(cert),
        san=_san_dns(cert)[:120],
        source=source,
        aia_ca_issuers=ca_issuer_urls(cert),
        ocsp_urls=ocsp_urls(cert),
        sct_count=_sct_count(cert),
        key_usage=_key_usage(cert),
        ext_key_usage=_ext_key_usage(cert),
    )


# ── Kehanet 1: kendi yol kurucumuz ────────────────────────────────────────────

def build_own_path(
    leaf: x509.Certificate, pool: list[x509.Certificate]
) -> tuple[list[x509.Certificate], str]:
    """İmzaları tek tek doğrulayarak yaprak → çıpa yolunu kurar.

    Bu, WebPKI doğrulayıcısından BAĞIMSIZ ikinci kehanettir. Doğrulayıcı
    CA/Browser Forum yaprak profilini dayatıyor (örn. AuthorityKeyIdentifier
    zorunlu); gerçek dünyadaki cPanel/Plesk self-signed ve iç CA sertifikaları
    bunu taşımaz. Yalnız doğrulayıcıya bakarsak o sertifikalar sebepsizce
    "hiçbir platformda güvenilmiyor" görünür.

    Döner: (yol, sonuç) — sonuç: `koke_ulasti` | `kendinden_imzali` |
    `eksik_halka` | `imza_dogrulanamadi`
    """
    anchor_by_subject: dict = {}
    for name in STORE_NAMES:
        entry = get_store(name)
        if entry:
            for c in entry[1]:
                anchor_by_subject.setdefault(c.subject, c)

    path = [leaf]
    cur = leaf
    seen = {_fp(leaf)}

    for _ in range(MAX_CHAIN_CERTS):
        if cur.subject == cur.issuer:
            return path, "kendinden_imzali"

        cands = [
            c for c in pool
            if c.subject == cur.issuer and _fp(c) not in seen
        ]
        anchor = anchor_by_subject.get(cur.issuer)
        if anchor is not None and _fp(anchor) not in seen:
            cands.append(anchor)

        issuer = None
        for cand in cands:
            try:
                cur.verify_directly_issued_by(cand)
                issuer = cand
                break
            except Exception:  # noqa: BLE001 — imza tutmayan aday atlanır
                continue

        if issuer is None:
            if cands:
                return path, "imza_dogrulanamadi"
            return path, "eksik_halka"

        path.append(issuer)
        seen.add(_fp(issuer))
        if anchor is not None and _fp(issuer) == _fp(anchor):
            return path, "koke_ulasti"
        cur = issuer

    return path, "eksik_halka"


# ── Kehanet 2: WebPKI doğrulayıcısı ───────────────────────────────────────────

def _relaxed_ee_policy() -> ExtensionPolicy:
    """Yaprakta AuthorityKeyIdentifier zorunluluğunu kaldırır.

    Varsayılan profil AKI'yi ŞART koşuyor; tarayıcılar koşmuyor. Gevşetmezsek
    AKI taşımayan her self-signed / iç CA sertifikası, gerçek sebebi
    gizleyen bir "geçersiz uzantı 2.5.29.35" hatasıyla düşer.
    """
    return ExtensionPolicy.webpki_defaults_ee().may_be_present(
        x509.AuthorityKeyIdentifier, Criticality.NON_CRITICAL, None
    )


def verify_webpki(
    store: Store,
    leaf: x509.Certificate,
    intermediates: list[x509.Certificate],
    host: str,
    now: datetime.datetime,
) -> tuple[bool, str]:
    """(başarılı_mı, ham_hata_metni). Doğrulayıcı HER ÇAĞRIDA yeniden kurulur.

    `build_server_verifier()` geçerlilik zamanını o an dondurur; süreç
    haftalarca ayakta kaldığı için önbelleğe alınmış bir doğrulayıcı, süresi
    dolmuş sertifikaları geçerli göstermeye başlar.
    """
    try:
        verifier = (
            PolicyBuilder()
            .store(store)
            .time(now)
            .extension_policies(
                ca_policy=ExtensionPolicy.webpki_defaults_ca(),
                ee_policy=_relaxed_ee_policy(),
            )
            .build_server_verifier(DNSName(host))
        )
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"

    try:
        verifier.verify(leaf, intermediates)
        return True, ""
    except VerificationError as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


# ── Platform matrisi ──────────────────────────────────────────────────────────
#
# "gecis" sütunu, o platformun EKSİK ARA SERTİFİKAYI kendi başına indirip
# indirmediğini söyler:
#
#   A → AIA çekmez. Yalnızca sunucunun gönderdiği zinciri görür.
#   B → AIA çeker. Eksik halkayı kendi tamamlar.
#   F → Firefox: AIA çekmez ama CCADB'den ara sertifika ön-yükler. O liste
#       auth arkasında olduğu için modellenemiyor; A ile B ayrışıyorsa
#       sonuç dürüstçe "belirsiz" raporlanır.
#
# Android'in İKİ satır olması kritik: aynı telefonda Chrome'un açıp uygulamanın
# açmaması tam olarak bu ayrışmadır ve ticket'ı üreten şeydir.

PLATFORMS = (
    {
        "key": "android", "store": "android", "gecis": "A",
        "ad": "Android sistem",
        "kapsam": "WebView · OkHttp · native uygulamalar",
        "not": "Android'in sistem TrustManager'ı AIA çekmez; eksik ara sertifikayı kendi başına tamamlayamaz.",
    },
    {
        "key": "android7", "store": "android7", "gecis": "A",
        "ad": "Android 7 (eski cihaz)",
        "kapsam": "Nougat kök deposu",
        "not": "Eski cihaz vekili. Android 14'ten itibaren kök deposu Conscrypt modülüyle güncellenebiliyor; 13 ve öncesi OEM imajına sabit.",
    },
    {
        "key": "android_chrome", "store": "chrome", "gecis": "B",
        "ad": "Android Chrome",
        "kapsam": "Chrome 114+ kendi kök deposu",
        "not": "Chrome kendi doğrulayıcısını ve kök deposunu kullanır ve AIA çeker — bu yüzden aynı telefonda uygulamadan farklı davranabilir.",
    },
    {
        "key": "ios", "store": "apple", "gecis": "B",
        "ad": "iOS / macOS",
        "kapsam": "Safari ve sistem geneli",
        "not": "Apple AIA çeker, ama bu best-effort'tur: yavaş bağlantıda veya captive portal arkasında başarısız olabilir. Sunucu bundle'ını yine de düzeltin.",
    },
    {
        "key": "chrome", "store": "chrome", "gecis": "B",
        "ad": "Chrome / Edge (masaüstü)",
        "kapsam": "Chrome Root Program",
        "not": "",
    },
    {
        "key": "windows", "store": "microsoft", "gecis": "B",
        "ad": "Windows",
        "kapsam": "Schannel · Outlook · .NET",
        "not": "",
    },
    {
        "key": "firefox", "store": "mozilla", "gecis": "F",
        "ad": "Firefox",
        "kapsam": "Mozilla kök deposu",
        "not": "Firefox AIA çekmez ama CCADB'den ara sertifika ön-yükler ve daha önce gördüklerini önbelleğe alır. O liste kimlik doğrulama arkasında olduğundan bu araç kesin konuşamıyor.",
    },
)

VERDICT_GUVENILIR = "guvenilir"
VERDICT_GUVENILMEZ = "guvenilmez"
VERDICT_BELIRSIZ = "belirsiz"
VERDICT_BILINMIYOR = "bilinmiyor"


def platform_verdicts(
    leaf: x509.Certificate,
    sent_inter: list[x509.Certificate],
    aia_inter: list[x509.Certificate],
    host: str,
    now: datetime.datetime,
) -> list[dict]:
    """Her platform için A ve B geçişlerini çalıştırıp kararı üretir."""
    store_results: dict[str, tuple] = {}
    for name in {p["store"] for p in PLATFORMS}:
        entry = get_store(name)
        if entry is None:
            store_results[name] = None
            continue
        store = entry[0]
        ok_a, err_a = verify_webpki(store, leaf, sent_inter, host, now)
        if aia_inter:
            ok_b, err_b = verify_webpki(store, leaf, sent_inter + aia_inter, host, now)
        else:
            ok_b, err_b = ok_a, err_a
        store_results[name] = (ok_a, err_a, ok_b, err_b)

    rows = []
    for p in PLATFORMS:
        res = store_results.get(p["store"])
        if res is None:
            rows.append({
                **{k: p[k] for k in ("key", "ad", "kapsam", "gecis")},
                "sonuc": VERDICT_BILINMIYOR,
                "sunucu_zinciri": VERDICT_BILINMIYOR,
                "aia_onarimli": VERDICT_BILINMIYOR,
                "aciklama": "Bu platformun kök deposu yüklenemedi.",
                "not": p["not"],
                "teknik": "",
            })
            continue

        ok_a, err_a, ok_b, err_b = res
        va = VERDICT_GUVENILIR if ok_a else VERDICT_GUVENILMEZ
        vb = VERDICT_GUVENILIR if ok_b else VERDICT_GUVENILMEZ

        if p["gecis"] == "A":
            sonuc, teknik = va, err_a
            if not ok_a and ok_b:
                aciklama = (
                    "Sunucunun gönderdiği zincir eksik. Bu platform eksik ara "
                    "sertifikayı kendi indiremediği için bağlantı BAŞARISIZ olur."
                )
            elif ok_a:
                aciklama = "Sunucunun gönderdiği zincir bu platformda doğrulanıyor."
            else:
                aciklama = "Zincir bu platformun kök deposuna kadar kurulamıyor."
        elif p["gecis"] == "B":
            sonuc, teknik = vb, err_b
            if ok_b and not ok_a:
                aciklama = (
                    "Sunucunun zinciri eksik ama bu platform eksik halkayı AIA ile "
                    "kendisi indirip onarıyor — sorun görünmez kalıyor."
                )
            elif ok_b:
                aciklama = "Zincir bu platformda doğrulanıyor."
            else:
                aciklama = "Zincir, AIA onarımından sonra bile bu platformda doğrulanamıyor."
        else:  # Firefox
            if ok_a:
                sonuc, teknik = VERDICT_GUVENILIR, ""
                aciklama = "Sunucunun gönderdiği zincir doğrulanıyor."
            elif ok_b:
                sonuc, teknik = VERDICT_BELIRSIZ, err_a
                aciklama = (
                    "Zincir eksik. Firefox eksik ara sertifikayı ön-yüklediyse açar, "
                    "yüklemediyse açmaz — bu araç kesin konuşamıyor."
                )
            else:
                sonuc, teknik = VERDICT_GUVENILMEZ, err_b
                aciklama = "Zincir bu platformda doğrulanamıyor."

        rows.append({
            **{k: p[k] for k in ("key", "ad", "kapsam", "gecis")},
            "sonuc": sonuc,
            "sunucu_zinciri": va,
            "aia_onarimli": vb,
            "aciklama": aciklama,
            "not": p["not"],
            "teknik": teknik,
        })
    return rows


# ── Önerilen zincir ───────────────────────────────────────────────────────────

def build_recommended_pem(path: list[x509.Certificate]) -> str:
    """Kurulacak fullchain.pem — doğru sırada, kök çıkarılmış.

    Bilinçli bir tercih: birden fazla geçerli yol olabilir. Let's Encrypt'in
    bugünkü `yaprak → YR2 → çapraz imzalı Root YR` zinciri buna örnek. Tarihî
    örnek ISRG Root X1 / DST Root X3: çapraz imzalı zinciri sunmak eski
    Android'i düzeltirken iOS/macOS'u kırmıştı. Bu yüzden çıktı "doğru zincir"
    diye değil, "en geniş uyumluluk için" diye etiketlenir.

    Kök çıkarılır: istemci köke zaten sahip olmalı; göndermek her el
    sıkışmada boşa 1-2 KB'dir.
    """
    out = []
    for i, cert in enumerate(path):
        if i > 0 and cert.subject == cert.issuer:
            continue  # kendinden imzalı kök — gönderilmez
        out.append(cert.public_bytes(Encoding.PEM).decode("ascii"))
    return "".join(out)


# ── Analiz ────────────────────────────────────────────────────────────────────

def _analyze_structure(
    sent: list[x509.Certificate],
    path: list[x509.Certificate],
    path_result: str,
    aia_certs: list[x509.Certificate],
    now: datetime.datetime,
) -> list[Finding]:
    out: list[Finding] = []
    if not sent:
        return out

    inter = sent[1:]

    # ── Sıra ──────────────────────────────────────────────────────────────
    # RFC 8446 gevşetti: yaprak İLK olmalı (MUST), gerisi sıralı olmalı
    # (SHOULD). OpenSSL, NSS ve Schannel sırasız araları tolere ediyor —
    # bu yüzden `error` değil `warning`.
    bozuk = [
        i for i in range(len(sent) - 1)
        if sent[i].issuer != sent[i + 1].subject
    ]
    if bozuk:
        out.append(Finding(
            label="Zincir sırası bozuk",
                oncelik=25,
            status="warning",
            detail=(
                f"{bozuk[0] + 1}. ve {bozuk[0] + 2}. sertifikalar birbirini takip "
                "etmiyor. Modern tarayıcılar sıralamayı düzeltir; bazı eski ve "
                "gömülü istemciler (Java, OkHttp'nin eski sürümleri) düzeltmez."
            ),
            fix="fullchain dosyasında sıra: yaprak → ara → (varsa) üst ara.",
        ))
    elif len(sent) > 1:
        out.append(Finding(
            label="Zincir sırası",
            status="healthy",
            detail="Sertifikalar doğru sırada gönderilmiş.",
        ))

    # ── Eksik ara sertifika — Android'i kıran asıl hata ───────────────────
    if path_result == "eksik_halka" and not aia_certs:
        out.append(Finding(
            label="Zincir tamamlanamıyor",
                oncelik=5,
            status="error",
            detail=(
                "Sunucunun gönderdiği sertifikalarla köke ulaşılamıyor ve eksik "
                "halka AIA üzerinden de indirilemedi."
            ),
            fix="CA'nızın verdiği ara sertifikaları fullchain dosyasına ekleyin.",
        ))
    elif aia_certs:
        adlar = ", ".join(_short_name(c) for c in aia_certs)
        out.append(Finding(
            label="Ara sertifika eksik",
                oncelik=5,
            status="error",
            detail=(
                f"Sunucu {len(aia_certs)} ara sertifikayı göndermiyor ({adlar}); "
                "zincir ancak AIA'dan indirilerek tamamlanabildi. Android sistem "
                "istemcileri AIA çekmediği için bu sitede BAŞARISIZ olur; "
                "masaüstü tarayıcılar sorunu görünmez kılar."
            ),
            fix="Aşağıdaki önerilen zinciri sunucuya kurun.",
        ))

    # ── Kök gönderilmiş mi ────────────────────────────────────────────────
    kokler = [c for c in inter if c.subject == c.issuer]
    for kok in kokler:
        if _not_after(kok) < now:
            # DST Root X3 senaryosu: süresi dolmuş bir kökü zincirde göndermek
            # OpenSSL 1.0.2 istemcilerini fiilen kırmıştı.
            out.append(Finding(
                label="Zincirde süresi dolmuş kök",
                oncelik=15,
                status="error",
                detail=(
                    f"'{_short_name(kok)}' kök sertifikası zincire eklenmiş ve "
                    f"süresi {_not_after(kok):%d.%m.%Y} tarihinde dolmuş. Eski "
                    "OpenSSL istemcileri bu yüzden bağlantıyı reddeder."
                ),
                fix="Kök sertifikayı fullchain dosyasından çıkarın.",
            ))
        else:
            out.append(Finding(
                label="Zincirde kök sertifika var",
                status="info",
                detail=(
                    f"'{_short_name(kok)}' kök sertifikası da gönderiliyor. Zararsız, "
                    "ama istemcide zaten var — her el sıkışmada boşa 1-2 KB."
                ),
                fix="İsterseniz fullchain dosyasından çıkarabilirsiniz.",
            ))

    # ── Tekrar / yabancı sertifika ────────────────────────────────────────
    seen: dict[str, int] = {}
    for c in sent:
        seen[_fp(c)] = seen.get(_fp(c), 0) + 1
    if any(v > 1 for v in seen.values()):
        out.append(Finding(
            label="Zincirde tekrarlanan sertifika",
            status="warning",
            detail="Aynı sertifika birden fazla kez gönderiliyor.",
            fix="fullchain dosyasındaki tekrarları temizleyin.",
        ))

    path_fps = {_fp(c) for c in path}
    yabanci = [c for c in inter if _fp(c) not in path_fps]
    if yabanci:
        out.append(Finding(
            label="Zincire ait olmayan sertifika",
            status="warning",
            detail=(
                f"{len(yabanci)} sertifika bu zincirin parçası değil: "
                + ", ".join(_short_name(c) for c in yabanci[:3])
                + ". Çoğu zaman birden fazla sitenin bundle'ı karışmış demektir."
            ),
            fix="fullchain dosyasında yalnızca bu sertifikanın zinciri olmalı.",
        ))

    if len(sent) > 1 and path_result == "imza_dogrulanamadi":
        out.append(Finding(
            label="Zincir imzası doğrulanamıyor",
                oncelik=8,
            status="error",
            detail=(
                "Gönderilen ara sertifika, yaprağı gerçekten imzalamamış. "
                "Genellikle başka bir sitenin bundle'ı kurulmuştur."
            ),
            fix="Bu alan adına ait CA bundle'ını yeniden kurun.",
        ))

    return out


def _analyze_certs(path: list[x509.Certificate], now: datetime.datetime) -> list[Finding]:
    out: list[Finding] = []
    for i, cert in enumerate(path):
        ad = _short_name(cert)
        nb, na = _not_before(cert), _not_after(cert)
        kendinden_imzali = cert.subject == cert.issuer

        if na < now:
            out.append(Finding(
                label=f"Süresi dolmuş: {ad}",
                status="error",
                detail=f"Geçerlilik {na:%d.%m.%Y} tarihinde bitmiş.",
                fix="Sertifikayı yenileyin.",
                oncelik=12 if i == 0 else 14,
            ))
        elif nb > now:
            out.append(Finding(
                label=f"Henüz geçerli değil: {ad}",
                status="error",
                detail=f"Geçerlilik {nb:%d.%m.%Y} tarihinde başlıyor. Sunucu saati yanlış olabilir.",
            ))

        # SHA-1: kökler MUAF. Kökler imzayla değil kimlikle güvenilir ve hâlâ
        # güvenilen bazı kökler SHA-1 kendinden imzalı. Muaf tutmazsak sağlam
        # bir zincire ölümcül karar veririz.
        sig = _sig_alg(cert)
        if sig in ("SHA1", "MD5") and not (kendinden_imzali and _is_ca(cert)):
            out.append(Finding(
                label=f"Zayıf imza algoritması: {ad}",
                status="error",
                detail=f"{sig} ile imzalanmış. Tüm modern tarayıcılar ve Android 7+ reddeder.",
                fix="CA'dan SHA-256 imzalı sertifika isteyin.",
                oncelik=20,
            ))

        algo, size = _key_info(cert)
        if algo == "RSA" and size and size < 2048:
            out.append(Finding(
                label=f"Zayıf anahtar: {ad}",
                status="error",
                detail=f"RSA {size} bit — asgari 2048 bit gerekiyor.",
                fix="En az 2048 bit RSA veya P-256 EC anahtarla yeniden oluşturun.",
                oncelik=20,
            ))

        # Ara sertifikada keyCertSign yoksa o sertifika imza atamaz.
        if i > 0 and _is_ca(cert):
            ku = _key_usage(cert)
            if ku and "keyCertSign" not in ku:
                out.append(Finding(
                    label=f"CA yetkisi eksik: {ad}",
                    status="error",
                    detail="Ara sertifikanın KeyUsage alanında keyCertSign yok — sertifika imzalayamaz.",
                ))

    # Zincirin etkin bitişi — "bugün çalışıyor, 3 ay sonra bozulacak" vakası.
    if len(path) > 1:
        leaf_end = _not_after(path[0])
        erken = [c for c in path[1:] if _not_after(c) < leaf_end and c.subject != c.issuer]
        if erken:
            en_erken = min(erken, key=_not_after)
            out.append(Finding(
                label="Ara sertifika yapraktan önce bitiyor",
                oncelik=28,
                status="warning",
                detail=(
                    f"'{_short_name(en_erken)}' {_not_after(en_erken):%d.%m.%Y} tarihinde "
                    f"bitiyor; yaprak sertifika ise {leaf_end:%d.%m.%Y}. Zincir o tarihte "
                    "yaprak hâlâ geçerliyken kırılır."
                ),
                fix="CA'nızdan güncel ara sertifikayı alıp bundle'ı yenileyin.",
            ))
    return out


def _analyze_leaf(
    leaf: x509.Certificate, host: str, now: datetime.datetime, ocsp_stapled: bool
) -> list[Finding]:
    out: list[Finding] = []
    san = _san_dns(leaf)
    cn = _attr(leaf.subject, NameOID.COMMON_NAME)

    if not san:
        out.append(Finding(
            label="SAN alanı yok",
                oncelik=10,
            status="error",
            detail=(
                "Sertifikada Subject Alternative Name yok"
                + (f" (yalnızca Common Name var: {cn})" if cn else "")
                + ". Chrome 58+, Android N+ ve iOS 13+ Common Name alanına hiç "
                "bakmaz — sertifika hiçbir modern tarayıcıda kabul edilmez."
            ),
            fix="CA'dan SAN içeren bir sertifika isteyin.",
        ))
    elif not any(_host_matches(p, host) for p in san):
        out.append(Finding(
            label="Alan adı eşleşmiyor",
                oncelik=10,
            status="error",
            detail=(
                f"Sertifika '{host}' için geçerli değil. Kapsadığı adlar: "
                + ", ".join(san[:8]) + ("…" if len(san) > 8 else "")
            ),
            fix="Bu alan adını kapsayan bir sertifika kurun.",
        ))
    else:
        out.append(Finding(
            label="Alan adı eşleşmesi",
            status="healthy",
            detail=f"'{host}' sertifikanın kapsamında.",
        ))

    eku = _ext_key_usage(leaf)
    if eku and "serverAuth" not in eku:
        out.append(Finding(
            label="serverAuth yetkisi yok",
                oncelik=18,
            status="error",
            detail="Sertifikanın ExtendedKeyUsage alanında serverAuth yok — TLS sunucu sertifikası olarak kullanılamaz.",
        ))

    # Geçerlilik süresi — SC-081v3 kademeli takvimi.
    nb, na = _not_before(leaf), _not_after(leaf)
    gun = (na - nb).days
    limit = _validity_limit_days(nb)
    if gun > limit:
        out.append(Finding(
            label="Geçerlilik süresi çok uzun",
                oncelik=35,
            status="error",
            detail=(
                f"{gun} gün geçerli. {nb:%d.%m.%Y} tarihinde kesilen bir sertifika için "
                f"azami süre {limit} gün (CA/Browser Forum SC-081v3). Apple ve Chrome "
                "bu sertifikayı reddeder."
            ),
            fix="CA'dan süre sınırına uyan yeni bir sertifika isteyin.",
        ))

    # CT / SCT — sayı raporlanır, ASLA `error` verilmez. SCT'ler TLS eklentisi
    # veya stapled OCSP ile de gelebilir; bu araç ikisini de göremez.
    sct = _sct_count(leaf)
    if sct == 0:
        out.append(Finding(
            label="Gömülü CT kaydı yok",
                oncelik=60,
            status="warning",
            detail=(
                "Sertifikada gömülü SCT (Certificate Transparency) yok. Apple ve "
                "Chrome CT şartı arar. SCT'ler TLS eklentisi veya OCSP ile de "
                "sunulabilir — bu araç o iki yolu göremediği için kesin konuşamıyor."
            ),
        ))
    else:
        out.append(Finding(
            label="Certificate Transparency",
            status="healthy",
            detail=f"{sct} gömülü SCT kaydı var.",
        ))

    # OCSP stapling — YALNIZCA bilgi. Let's Encrypt Mayıs 2025'te sertifikalardan
    # OCSP URL'ini çıkardı, Ağustos 2025'te yanıtlayıcılarını kapattı. Uyarı
    # vermek Türkiye'deki neredeyse her LE sertifikasında yalancı alarm olur.
    out.append(Finding(
        label="OCSP stapling",
        status="info",
        detail=(
            "Sunucu OCSP yanıtını zımbalıyor."
            if ocsp_stapled
            else "Sunucu OCSP yanıtı zımbalamıyor. Sorun değil — sektör OCSP'yi terk ediyor."
        ),
    ))
    return out


# ── Üst düzey ─────────────────────────────────────────────────────────────────

def analyze(
    host: str,
    port: int,
    hs: HandshakeResult,
    aia_certs: list[x509.Certificate],
    aia_findings: list[Finding],
    no_sni_leaf_fp: Optional[str],
    now: Optional[datetime.datetime] = None,
) -> dict:
    """Tüm parçaları birleştirip arayüzün göstereceği yapıyı üretir.

    CPU işi (6 depoya karşı 2 geçiş doğrulama ≈ 15 ms) — executor'da çağrılır.
    """
    from dataclasses import asdict

    now = now or datetime.datetime.now(datetime.timezone.utc)
    sent = hs.certs
    if not sent:
        raise ValueError("Sunucu hiç sertifika göndermedi")

    leaf = sent[0]
    sent_inter = sent[1:]
    pool = sent + aia_certs

    path, path_result = build_own_path(leaf, pool)

    bulgular: list[Finding] = []
    bulgular += store_health_findings()

    # El sıkışma bilgisi
    if hs.protocol:
        eski = hs.protocol in ("TLSv1", "TLSv1.1", "SSLv3")
        bulgular.append(Finding(
            label="TLS sürümü",
            status="warning" if eski else "info",
            detail=(
                f"Sunucu {hs.protocol} konuşuyor ({hs.cipher}). Modern tarayıcılar "
                "TLS 1.0/1.1'i devre dışı bıraktı — kullanıcılar bağlanamaz."
                if eski else f"{hs.protocol} · {hs.cipher}"
            ),
            fix="Sunucuda TLS 1.2 ve 1.3'ü açın." if eski else "",
        ))

    if hs.truncated:
        bulgular.append(Finding(
            label="Zincir çok uzun",
            status="warning",
            detail=f"Sunucu {MAX_CHAIN_CERTS}'den fazla sertifika gönderdi; fazlası incelenmedi.",
        ))
    if hs.leaf_mismatch:
        bulgular.append(Finding(
            label="Zincirin ilk sertifikası yaprak değil",
            status="warning",
            detail="Sunucu zinciri, sunucu sertifikasıyla başlamıyor. Bazı istemciler bunu reddeder.",
            fix="fullchain dosyasında ilk sertifika sunucu sertifikası olmalı.",
        ))

    bulgular += _analyze_structure(sent, path, path_result, aia_certs, now)
    bulgular += _analyze_certs(path, now)
    bulgular += _analyze_leaf(leaf, host, now, hs.ocsp_stapled)
    bulgular += aia_findings

    # Zincir kendinden imzalı bir sertifikada bitiyor ama o sertifika HİÇBİR
    # kök deposunda yok. build_own_path bilinen bir çıpaya varsaydı
    # "koke_ulasti" dönerdi; "kendinden_imzali" + uzunluk>1 tam olarak bu
    # demek. İki kehanetin ayrıştığı yer: zincir kriptografik olarak tutarlı
    # (bizim yol kurucumuz kurdu) ama WebPKI'da karşılığı yok.
    if path_result == "kendinden_imzali" and len(path) > 1:
        kok = path[-1]
        bulgular.append(Finding(
            label="Zincirin kökü hiçbir güven deposunda yok",
            status="error",
            oncelik=8,
            detail=(
                f"Zincir '{_short_name(kok)}' kök sertifikasında bitiyor; bu kök "
                "Apple, Android, Chrome, Microsoft ve Mozilla depolarının hiçbirinde "
                "yer almıyor. İmzalar tutarlı — yani sertifika teknik olarak sağlam — "
                "ama hiçbir tarayıcı bu köke güvenmez."
            ),
            fix="Herkesçe tanınan bir CA'dan (ör. ücretsiz Let's Encrypt) sertifika alın.",
        ))

    # Kendinden imzalı / iç CA — iki kehanetin ayrıştığı yer.
    if path_result == "kendinden_imzali" and len(path) == 1:
        bulgular.append(Finding(
            label="Kendinden imzalı sertifika",
                oncelik=12,
            status="error",
            detail=(
                "Sertifika kendi kendini imzalamış; hiçbir genel güven deposunda "
                "karşılığı yok. Zincir kriptografik olarak tutarlı ama hiçbir "
                "tarayıcı güvenmez."
            ),
            fix="Ücretsiz Let's Encrypt dahil, herkesçe tanınan bir CA'dan sertifika alın.",
        ))

    # SNI'siz el sıkışma farkı.
    #
    # Bunu `warning` yapmıyoruz: SNI göndermeyen istemciler (Android 2.x,
    # Windows XP/IE) pratikte tükendi ve sunucunun SNI'siz farklı bir vhost
    # sunması normaldir. Her sitede uyarı basmak yalancı alarmdır. Yine de
    # paylaşımlı hosting'de sorulan bir soru olduğu için bilgi olarak durur.
    if no_sni_leaf_fp is not None:
        if no_sni_leaf_fp != _fp(leaf):
            bulgular.append(Finding(
                label="Site SNI gerektiriyor",
                status="info",
                detail=(
                    "SNI göndermeyen istemciler bu sunucudan başka bir sertifika "
                    "alıyor. Modern istemcilerin tamamı SNI gönderir; yalnızca "
                    "Android 2.x ve Windows XP gibi tükenmiş istemcileri etkiler."
                ),
            ))
        else:
            bulgular.append(Finding(
                label="SNI'siz erişim",
                status="healthy",
                detail="SNI göndermeyen istemciler de doğru sertifikayı alıyor.",
            ))

    platformlar = platform_verdicts(leaf, sent_inter, aia_certs, host, now)

    # ── Zincir görünümü ───────────────────────────────────────────────────
    aia_fps = {_fp(c) for c in aia_certs}
    zincir = []
    for i, cert in enumerate(path):
        if i == 0:
            rol = "yaprak"
        elif cert.subject == cert.issuer:
            rol = "kök"
        else:
            rol = "ara"
        kaynak = "AIA" if _fp(cert) in aia_fps else (
            "sunucu" if any(_fp(cert) == _fp(c) for c in sent) else "güven deposu"
        )
        zincir.append(asdict(cert_info(cert, i, rol, kaynak, now)))

    # ── Özet ──────────────────────────────────────────────────────────────
    hata = [f for f in bulgular if f.status == "error"]
    uyari = [f for f in bulgular if f.status == "warning"]

    pk = {p["key"]: p for p in platformlar}

    def _ok(key):
        return pk.get(key, {}).get("sonuc") == VERDICT_GUVENILIR

    def _kirik(key):
        return pk.get(key, {}).get("sonuc") == VERDICT_GUVENILMEZ

    # Eski cihaz kök boşluğu: zincir eksiksiz ama Nougat deposunda kök yok.
    # Eksik ara sertifikadan TAMAMEN farklı bir sorun — ayrı raporlanmalı,
    # yoksa teknisyen yanlış şeyi düzeltmeye çalışır.
    if _ok("android") and _kirik("android7"):
        bulgular.append(Finding(
            label="Eski Android cihazlarda güvenilmiyor",
                oncelik=22,
            status="warning",
            detail=(
                "Zincir eksiksiz, ama sertifikanın kökü Android 7 ve öncesinin kök "
                "deposunda yok. O cihazlar siteye giremez. Bu, eksik ara "
                "sertifikadan farklı bir sorundur — sunucu yapılandırmasıyla çözülmez."
            ),
            fix="Eski cihazlar hedef kitleyseniz CA'nızdan daha eski, yaygın bir köke zincirlenen sertifika isteyin.",
        ))

    # "Android'de kırık" başlığı YALNIZCA sebebi eksik ara sertifikaysa.
    # badssl.com gibi zinciri eksiksiz ama kökü eski depoda olmayan siteler
    # bu başlığı almamalı.
    eksik_ara_yuzunden = bool(aia_certs) and _kirik("android") and _ok("ios")

    if eksik_ara_yuzunden:
        durum = "error"
        baslik = "Android'de kırık, masaüstünde çalışıyor"
        ozet = (
            "Sunucu zinciri eksik gönderiyor. Masaüstü tarayıcılar ve iOS eksik ara "
            "sertifikayı kendileri indirip onarıyor, bu yüzden sorun görünmez kalıyor; "
            "Android sistem istemcileri AIA çekmediği için bağlantı kuramıyor."
        )
    elif hata:
        durum = "error"
        baslik = "Zincirde hata var"
        oncelikli = min(hata, key=lambda f: f.oncelik)
        ozet = oncelikli.detail or oncelikli.label
    elif _ok("android") and _kirik("android7"):
        durum = "warning"
        baslik = "Eski Android cihazlarda güvenilmiyor"
        ozet = (
            "Zincir eksiksiz ve güncel cihazlarda sorunsuz, ama sertifikanın kökü "
            "Android 7 ve öncesinin kök deposunda yok."
        )
    elif uyari:
        durum = "warning"
        baslik = "Zincir çalışıyor, iyileştirilebilir"
        oncelikli = min(uyari, key=lambda f: f.oncelik)
        ozet = oncelikli.detail or oncelikli.label
    else:
        durum = "healthy"
        baslik = "Zincir eksiksiz ve tüm platformlarda geçerli"
        ozet = "Sunucu tam zinciri doğru sırada gönderiyor; test edilen tüm kök depolarında doğrulanıyor."

    onerilen = build_recommended_pem(path)
    meta = load_store_meta()

    return {
        "domain": host,
        "port": port,
        "durum": durum,
        "baslik": baslik,
        "ozet": ozet,
        "protokol": hs.protocol,
        "sifre_suiti": hs.cipher,
        "ocsp_stapling": hs.ocsp_stapled,
        "sunulan_sertifika_sayisi": len(sent),
        "aia_ile_eklenen": len(aia_certs),
        "zincir_sonucu": path_result,
        "zincir": zincir,
        "platformlar": platformlar,
        "bulgular": [asdict(f) for f in bulgular],
        "onerilen_pem": onerilen,
        "onerilen_pem_not": (
            "En geniş uyumluluk için önerilen zincir: yaprak + ara sertifikalar, "
            "doğru sırada, kök çıkarılmış. Birden fazla geçerli yol olabilir "
            "(çapraz imzalı kökler); bu çıktı eski cihaz uyumluluğunu değil, "
            "test edilen kök depolarının tamamında doğrulanmayı hedefler."
        ),
        "depo_bilgisi": {
            "uretim_tarihi": meta.get("generated_at", ""),
            "sayilar": meta.get("counts", {}),
        },
    }
