"""Genel Bakış — bir alan adının tüm sağlık başlıklarını tek çağrıda toplar.

Panel bugüne kadar ARAÇ merkezliydi: teknisyen "example.com sorunlu" diyen bir
çağrıda sekiz sekmeyi tek tek gezmek zorundaydı. Oysa destek çağrısı ALAN ADI
merkezlidir. Bu uç, bir alan adı için ucuz kontrollerin hepsini paralel
çalıştırıp tek bir sağlık tablosu döndürür ve "önce şu araca bak" der.

Yeni kontrol mantığı YAZILMADI — mevcut router'ların `do_*` coroutine'leri
doğrudan çağrılıyor. Kontrol mantığının iki kopyası olsaydı biri düzeltilip
diğeri unutulduğunda panel kendi kendisiyle çelişen sonuçlar üretirdi.

Aynı motor üç yerde kullanılır:
  • Genel Bakış panosu (etkileşimli)
  • Müşteri Raporu (yazdırılabilir çıktı)
  • Toplu kontrol (N alan adı için ardışık çağrı)

Site hızı BİLEREK dışarıda: 30-60 saniye sürüyor ve tarayıcı başlatıyor.
Pano saniyeler içinde açılmalı; hız ölçümü ayrı bir düğmeyle tetiklenir.
"""

import asyncio
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import dns_core
from dns_core import kayit_alan_adi
from net_validation import resolve_public_ips_async
from rate_limiter import limiter
from routers import blacklist as bl
from routers.quick_check import (
    CheckItem, do_dns_a, do_dns_mx, do_dns_ns, do_http, do_ssl, do_whois,
    validate_domain,
)

router = APIRouter(prefix="/api/genel-bakis", tags=["genel-bakis"])

# Tüm kontroller için toplam duvar saati sınırı. Tek tek kontrollerin kendi
# zaman aşımları var; bu, hepsinin birden takılmasına karşı son emniyet.
_TOPLAM_TIMEOUT = 40.0

# Blacklist taraması pahalı (onlarca DNS sorgusu). Panoda yalnızca en yaygın
# birkaç zone'a bakılır; tam tarama için Blacklist aracı var.
_HIZLI_RBL_SAYISI = 8


class GenelBakisIstegi(BaseModel):
    domain: str = Field(..., max_length=253)


class Kart(BaseModel):
    """Panoda tek bir sağlık kutusu."""
    id: str
    baslik: str
    durum: str                      # healthy | warning | error | info
    deger: Optional[str] = None
    detay: Optional[str] = None
    arac: Optional[str] = None      # tıklanınca gidilecek aracın TOOLS id'si
    oncelik: int = 5                # 1 = en acil; "önce şuna bak" sıralaması


class GenelBakisYaniti(BaseModel):
    domain: str
    kayit_alan_adi: str             # WHOIS/NS/SPF/DMARC bunun üzerinden sorgulandı
    alt_alan_mi: bool
    genel_durum: str
    ozet: str
    kartlar: list[Kart]
    checks: list[CheckItem]         # quick_check ile AYNI sözleşme
    http_status: Optional[int] = None
    sonraki_adim: Optional[str] = None
    sure_ms: int


def _durum_agirligi(d: str) -> int:
    return {"error": 0, "warning": 1, "info": 2, "healthy": 3}.get(d, 4)


async def _guvenli(coro, yedek_etiket: str) -> CheckItem:
    """Tek bir kontrolün çökmesi tüm panoyu düşürmesin."""
    try:
        sonuc = await coro
        return sonuc[0] if isinstance(sonuc, tuple) else sonuc
    except HTTPException as e:
        return CheckItem(label=yedek_etiket, status="error", detail=str(e.detail))
    except Exception as e:
        return CheckItem(label=yedek_etiket, status="info",
                         detail=f"Kontrol tamamlanamadı: {type(e).__name__}")


async def _eposta_karti(domain: str) -> Kart:
    """SPF ve DMARC varlığı — tam analiz için Mail Sağlığı aracı var."""
    try:
        spf_res, dmarc_res = await asyncio.gather(
            dns_core.resolve_async(domain, "TXT", timeout=5.0),
            dns_core.resolve_async(f"_dmarc.{domain}", "TXT", timeout=5.0),
        )
        spf = [r for r in spf_res["records"] if r.lower().startswith("v=spf1")]
        dmarc = [r for r in dmarc_res["records"] if r.lower().startswith("v=dmarc1")]

        eksik = []
        if not spf:
            eksik.append("SPF")
        if not dmarc:
            eksik.append("DMARC")

        if not eksik:
            # SPF birden fazlaysa RFC ihlali — tümü geçersiz sayılır
            if len(spf) > 1:
                return Kart(id="eposta", baslik="E-posta", durum="error",
                            deger=f"{len(spf)} adet SPF",
                            detay="Birden fazla SPF kaydı var — RFC'ye göre hepsi geçersiz sayılır.",
                            arac="mail-health", oncelik=2)
            return Kart(id="eposta", baslik="E-posta", durum="healthy",
                        deger="SPF + DMARC var",
                        detay="Temel e-posta kimlik doğrulama kayıtları yerinde.",
                        arac="mail-health", oncelik=5)

        return Kart(id="eposta", baslik="E-posta", durum="warning",
                    deger=f"{' ve '.join(eksik)} yok",
                    detay="Eksik kayıtlar e-postaların spam'e düşme riskini artırır.",
                    arac="mail-health", oncelik=3)
    except Exception:
        return Kart(id="eposta", baslik="E-posta", durum="info",
                    deger="Kontrol edilemedi", arac="mail-health", oncelik=5)


async def _blacklist_karti(domain: str) -> Kart:
    """Yaygın RBL'lerde hızlı tarama. Tam liste için Blacklist aracı."""
    try:
        ipler = await bl._resolve_target_ips(domain)
        if not ipler:
            return Kart(id="blacklist", baslik="Blacklist", durum="info",
                        deger="IP çözülemedi", arac="blacklist", oncelik=5)

        ip = ipler[0]
        resolver = bl._make_rbl_resolver()
        sem = asyncio.Semaphore(8)
        zonelar = bl.ZONES[:_HIZLI_RBL_SAYISI]
        sonuclar = await asyncio.gather(
            *[bl._check_zone(resolver, ip, z, sem) for z in zonelar],
            return_exceptions=True,
        )

        listeli = [s for s in sonuclar
                   if not isinstance(s, Exception) and getattr(s, "listed", False)]
        if listeli:
            adlar = ", ".join(getattr(s, "name", "?") for s in listeli[:3])
            return Kart(id="blacklist", baslik="Blacklist", durum="error",
                        deger=f"{len(listeli)} listede",
                        detay=f"{ip} şu listelerde: {adlar}. E-posta teslimatı engellenir.",
                        arac="blacklist", oncelik=1)
        return Kart(id="blacklist", baslik="Blacklist", durum="healthy",
                    deger="Temiz",
                    detay=f"{ip} yaygın {len(zonelar)} listede görünmüyor.",
                    arac="blacklist", oncelik=5)
    except HTTPException as e:
        return Kart(id="blacklist", baslik="Blacklist", durum="info",
                    deger="Kontrol edilemedi", detay=str(e.detail),
                    arac="blacklist", oncelik=5)
    except Exception:
        return Kart(id="blacklist", baslik="Blacklist", durum="info",
                    deger="Kontrol edilemedi", arac="blacklist", oncelik=5)


def _karta_cevir(item: CheckItem, kart_id: str, baslik: str,
                 arac: str, oncelik_haritasi: dict) -> Kart:
    return Kart(
        id=kart_id, baslik=baslik, durum=item.status,
        deger=item.value, detay=item.detail, arac=arac,
        oncelik=oncelik_haritasi.get(item.status, 5),
    )


@router.post("/", response_model=GenelBakisYaniti)
@limiter.limit("10/minute")
async def genel_bakis(request: Request, payload: GenelBakisIstegi):
    """Bir alan adının tüm sağlık başlıklarını paralel toplar."""
    domain = validate_domain(payload.domain)
    # Çözümleme kapısı burada; alt kontroller de kendi içinde doğruluyor ama
    # çözülemeyen bir hedefte sekiz ayrı kontrolü boşuna başlatmayalım.
    await resolve_public_ips_async(domain, 443)

    # Hedefi ikiye ayır. Alt alan adını apex gibi sorgulamak yanlış alarm
    # üretiyordu: www.X'in kendi NS'i, WHOIS kaydı ve SPF/DMARC'ı yoktur ve
    # olmaması NORMALDİR. Kayıt ve e-posta politikası apex'e, sertifika ile
    # HTTP erişimi ise kullanıcının yazdığı TAM HOSTA aittir.
    apex = kayit_alan_adi(domain)
    alt_alan_mi = apex != domain

    t0 = time.monotonic()
    try:
        (whois_i, ns_i, mx_i, eposta_k,
         a_i, ssl_i, http_ikili, blacklist_k) = await asyncio.wait_for(
            asyncio.gather(
                # apex: kayıt ve e-posta politikası
                _guvenli(do_whois(apex), "WHOIS / Alan Adı"),
                _guvenli(do_dns_ns(apex), "DNS / NS Kayıtları"),
                _guvenli(do_dns_mx(apex), "DNS / MX Kaydı"),
                _eposta_karti(apex),
                # tam host: adresleme, sertifika, erişim, itibar
                _guvenli(do_dns_a(domain), "DNS / A Kaydı"),
                _guvenli(do_ssl(domain), "SSL Sertifika"),
                _guvenli(do_http(domain), "HTTP Erişim"),
                _blacklist_karti(domain),
            ),
            timeout=_TOPLAM_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "Kontroller zaman aşımına uğradı — hedef çok yavaş yanıt veriyor.")

    http_i = http_ikili
    http_status = None
    if isinstance(http_i, CheckItem) and http_i.value:
        rakam = "".join(ch for ch in http_i.value if ch.isdigit())
        http_status = int(rakam) if rakam else None

    checks = [whois_i, ns_i, a_i, mx_i, ssl_i, http_i]

    # DNS kartı: üç DNS kontrolünün en kötüsü
    dns_items = [ns_i, a_i, mx_i]
    dns_en_kotu = min(dns_items, key=lambda i: _durum_agirligi(i.status))
    dns_kart = Kart(
        id="dns", baslik="DNS", durum=dns_en_kotu.status,
        deger=("Kayıtlar uyumlu" if dns_en_kotu.status == "healthy"
               else dns_en_kotu.label.replace("DNS / ", "")),
        detay=dns_en_kotu.detail, arac="dns-toolbox",
        oncelik={"error": 2, "warning": 3}.get(dns_en_kotu.status, 5),
    )

    kartlar = [
        _karta_cevir(whois_i, "alan-adi", "Alan Adı", "dns-history",
                     {"error": 1, "warning": 2}),
        _karta_cevir(ssl_i, "ssl", "SSL", "ssl-tools", {"error": 1, "warning": 2}),
        dns_kart,
        _karta_cevir(http_i, "http", "HTTP Erişim", "quick-check",
                     {"error": 1, "warning": 3}),
        eposta_k,
        blacklist_k,
    ]

    # Genel durum: en kötü kart belirler
    durumlar = [k.durum for k in kartlar]
    if "error" in durumlar:
        genel = "error"
    elif "warning" in durumlar:
        genel = "warning"
    else:
        genel = "healthy"

    sorunlular = sorted(
        [k for k in kartlar if k.durum in ("error", "warning")],
        key=lambda k: (k.oncelik, _durum_agirligi(k.durum)),
    )
    sonraki = sorunlular[0].arac if sorunlular else None

    if genel == "healthy":
        ozet = f"{domain} için tüm temel kontroller sağlıklı."
    else:
        basliklar = ", ".join(k.baslik for k in sorunlular[:3])
        ozet = (f"{domain} için {len(sorunlular)} başlıkta sorun var: {basliklar}"
                + ("…" if len(sorunlular) > 3 else "."))

    return GenelBakisYaniti(
        domain=domain, kayit_alan_adi=apex, alt_alan_mi=alt_alan_mi,
        genel_durum=genel, ozet=ozet,
        kartlar=kartlar, checks=checks, http_status=http_status,
        sonraki_adim=sonraki,
        sure_ms=int((time.monotonic() - t0) * 1000),
    )
