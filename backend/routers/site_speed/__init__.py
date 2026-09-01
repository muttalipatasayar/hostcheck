"""Site Hızı — PageSpeed benzeri performans ölçüm aracı.

Ölçüm 20-60 saniye sürdüğü için tek bir senkron istek yerine **iş + yoklama**
modeli kullanılıyor: `POST /run` bir iş kimliği döndürür, arayüz
`GET /job/{id}` ile ilerlemeyi canlı gösterir. Böylece teknisyen dönen bir
spinner yerine hangi aşamada olunduğunu görür ve uzun istek tarayıcı/proxy
zaman aşımına takılmaz.

İş deposu SÜREÇ İÇİDİR (`_ISLER`) — `rdp._tickets` ile aynı desen. Tek
worker varsayımına bağlıdır: `--workers 2` ile çalıştırılırsa yoklama isteği
işi başlatan sürece düşmeyebilir ve iş "kayıp" görünür. Servis birimi tek
worker'ı gerekçesiyle birlikte sabitliyor.

İki motor katmanı:
  1. Kendi Playwright ölçümümüz — her zaman çalışır, anahtar gerekmez
  2. Google PSI + CrUX — yalnızca `PAGESPEED_API_KEY` tanımlıysa
"""

import asyncio
import base64
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from net_validation import resolve_public_ips_async
from rate_limiter import limiter
from routers.quick_check import validate_domain

from . import advice, audits, engine, google, scoring, store, timing

router = APIRouter(prefix="/api/site-speed", tags=["site-speed"])

# ── Süreç içi iş deposu ──────────────────────────────────────────────────────
_ISLER: dict[str, dict] = {}
_IS_TTL = 600            # sn — bitmiş iş bu süre sonunda silinir
_MAX_IS = 50             # depoda tutulacak en fazla kayıt
_MAX_BEKLEYEN = 4        # aynı anda kuyrukta bekleyebilecek iş sayısı

_GECERLI_STRATEJILER = ("mobile", "desktop")


def _supur() -> None:
    """Süresi dolan işleri temizler ve depo sınırını uygular."""
    simdi = time.time()
    for anahtar in [k for k, v in _ISLER.items()
                    if simdi - v["olusturma"] > _IS_TTL]:
        _ISLER.pop(anahtar, None)

    while len(_ISLER) > _MAX_IS:
        en_eski = min(_ISLER, key=lambda k: _ISLER[k]["olusturma"])
        _ISLER.pop(en_eski, None)


def _bekleyen_sayisi() -> int:
    return sum(1 for v in _ISLER.values()
               if v["durum"] in ("kuyrukta", "calisiyor"))


class OlcumIstegi(BaseModel):
    domain: str = Field(..., max_length=253)
    stratejiler: list[str] | None = Field(
        default=None,
        description="mobile ve/veya desktop. Verilmezse ikisi de ölçülür.")


class IsYaniti(BaseModel):
    is_id: str


class IsDurumu(BaseModel):
    is_id: str
    durum: str                  # kuyrukta | calisiyor | bitti | hata
    ilerleme: int               # 0-100
    adim: str
    domain: str
    hata: str | None = None
    sonuc: dict | None = None


def _guncelle(is_id: str, *, ilerleme: int | None = None, adim: str | None = None,
              durum: str | None = None, hata: str | None = None,
              sonuc: dict | None = None) -> None:
    is_kaydi = _ISLER.get(is_id)
    if not is_kaydi:
        return
    if ilerleme is not None:
        is_kaydi["ilerleme"] = ilerleme
    if adim is not None:
        is_kaydi["adim"] = adim
    if durum is not None:
        is_kaydi["durum"] = durum
    if hata is not None:
        is_kaydi["hata"] = hata
    if sonuc is not None:
        is_kaydi["sonuc"] = sonuc


async def _strateji_olc(domain: str, strateji: str, baglanti: dict,
                        db: Session) -> dict:
    """Tek bir strateji için ölçüm + denetim + skor + Google + karşılaştırma."""
    olcum = await engine.olc(domain, strateji)

    metrikler = olcum["metrikler"]
    # Bağlantı ölçümü tarayıcınınkinden daha güvenilir (3 tekrarın medyanı,
    # emülasyondan etkilenmez). TTFB'yi oradan alıyoruz.
    med = (baglanti or {}).get("medyan") or {}
    # Tarayıcının ölçtüğü TTFB emülasyon gecikmesini de içerir — kullanıcının
    # yaşadığı gerçeklik odur, ama "sunucu yavaş mı" sorusunu cevaplamaz.
    # İkisini de tutuyoruz: kart bağlantı ölçümünü gösterir (3 tekrarın
    # medyanı, emülasyondan bağımsız), emüle değer ayrı alanda kalır.
    metrikler["ttfb_emulasyon_ms"] = metrikler.get("ttfb_ms")
    if med.get("ttfb_ms") is not None:
        metrikler["ttfb_ms"] = med["ttfb_ms"]

    # Lighthouse audit id'lerine çevirip skorla
    skor = scoring.performance_score({
        "first-contentful-paint":   metrikler.get("fcp_ms"),
        "largest-contentful-paint": metrikler.get("lcp_ms"),
        "total-blocking-time":      metrikler.get("tbt_ms"),
        "cumulative-layout-shift":  metrikler.get("cls"),
    }, strateji)

    denetimler = advice.zenginlestir(audits.calistir(olcum, baglanti, domain))

    toplam_bayt = sum(k.get("tel_bayt") or 0 for k in olcum.get("kaynaklar") or [])
    toplam_bayt += (olcum.get("navigasyon") or {}).get("encodedBodySize", 0)

    ss = olcum.get("ekran_goruntusu") or b""
    ekran = ("data:image/jpeg;base64," + base64.b64encode(ss).decode()) if ss else None

    sonuc = {
        "strateji": strateji,
        "skor": skor,
        "skor_durumu": scoring.score_status(skor),
        "metrikler": metrikler,
        "metrik_durumlari": {
            ad: scoring.metric_status(ad, metrikler.get(ad))
            for ad in ("lcp_ms", "cls", "tbt_ms", "fcp_ms", "ttfb_ms")
        },
        "lcp_detay": olcum.get("lcp_detay"),
        "cls_detay": olcum.get("cls_detay"),
        "navigasyon": olcum.get("navigasyon"),
        "denetimler": denetimler,
        "kaynaklar": olcum.get("kaynaklar") or [],
        "kaynak_sayisi": olcum.get("kaynak_sayisi", 0),
        "toplam_bayt": toplam_bayt,
        "dom_dugum_sayisi": olcum.get("dom_dugum_sayisi", 0),
        "son_url": olcum.get("son_url"),
        "baslik": olcum.get("baslik"),
        "ekran_goruntusu": ekran,
    }

    # Geçmişe yaz ve bir öncekiyle karşılaştır (yazmadan ÖNCE oku, yoksa
    # kendi kaydımızla karşılaştırırdık)
    try:
        onceki = store.onceki(db, domain, strateji)
        sonuc["karsilastirma"] = store.karsilastir(sonuc, onceki)
        store.kaydet(db, domain, strateji, sonuc, motor="yerel")
        sonuc["gecmis"] = store.gecmis(db, domain, strateji, limit=20)
    except Exception:
        # Geçmiş bir kolaylık; DB sorunu ölçümü çöpe atmamalı
        sonuc["karsilastirma"] = None
        sonuc["gecmis"] = []

    return sonuc


async def _calistir(is_id: str, domain: str, stratejiler: list[str]) -> None:
    """Arka plan görevi — ölçümü baştan sona yürütür."""
    db = SessionLocal()
    try:
        _guncelle(is_id, durum="calisiyor", ilerleme=5,
                  adim="Hedef doğrulanıyor…")

        _guncelle(is_id, ilerleme=12, adim="Bağlantı fazları ölçülüyor (DNS/TCP/TLS)…")
        baglanti = await timing.measure(domain)

        if not baglanti.get("ulasilabilir"):
            _guncelle(is_id, durum="hata",
                      hata=f"{domain} adresine bağlanılamadı. Site ayakta mı?")
            return

        sonuclar: dict[str, dict] = {}
        # İlerleme payı: bağlantı %15, Google %10, rapor %5 → stratejilere %70
        pay = 70 // max(1, len(stratejiler))
        taban = 15
        for i, strateji in enumerate(stratejiler):
            etiket = "Mobil" if strateji == "mobile" else "Masaüstü"
            _guncelle(is_id, ilerleme=taban + i * pay,
                      adim=f"{etiket} ölçüm yapılıyor (sayfa yükleniyor)…")
            sonuclar[strateji] = await _strateji_olc(domain, strateji, baglanti, db)

        if google.etkin():
            _guncelle(is_id, ilerleme=88, adim="Google verisi alınıyor (PSI + CrUX)…")
            for strateji in stratejiler:
                try:
                    psi_sonuc, crux_sonuc = await asyncio.gather(
                        google.psi(domain, strateji),
                        google.crux(domain, strateji),
                    )
                    sonuclar[strateji]["psi"] = psi_sonuc
                    sonuclar[strateji]["crux"] = crux_sonuc
                except Exception as e:
                    sonuclar[strateji]["psi"] = {
                        "hata": f"Google katmanı çalışmadı: {type(e).__name__}"}
                    sonuclar[strateji]["crux"] = None

        _guncelle(is_id, ilerleme=95, adim="Rapor hazırlanıyor…")

        _guncelle(is_id, durum="bitti", ilerleme=100, adim="Tamamlandı",
                  sonuc={
                      "domain": domain,
                      "olcum_zamani": time.time(),
                      "google_etkin": google.etkin(),
                      "baglanti": baglanti,
                      "stratejiler": sonuclar,
                      # Kendi motorumuzun sınırları — arayüz bunları yazıyor
                      "notlar": {
                          "speed_index": ("Speed Index ölçülmedi; ağırlıklar kalan "
                                          "dört metrik arasında yeniden normalize "
                                          "edildi. Skor resmî PSI'dan birkaç puan "
                                          "sapabilir."),
                          "inp": ("INP laboratuvar ortamında ölçülemez (gerçek "
                                  "kullanıcı etkileşimi gerekir). Yerine TBT "
                                  "gösteriliyor; gerçek INP yalnızca saha "
                                  "verisinden gelir."),
                          "kisitlama": ("Ölçüm mobilde 4× CPU ve yavaş 4G "
                                        "kısıtlamasıyla yapılır. Lighthouse simüle "
                                        "kısıtlama kullanır; sayılar yakındır ama "
                                        "birebir değildir."),
                      },
                  })
    except HTTPException as e:
        _guncelle(is_id, durum="hata", hata=str(e.detail))
    except Exception as e:
        mesaj = str(e)[:300] or type(e).__name__
        _guncelle(is_id, durum="hata", hata=f"Ölçüm başarısız: {mesaj}")
    finally:
        db.close()


@router.post("/run", response_model=IsYaniti)
@limiter.limit("5/minute")
async def olcum_baslat(request: Request, payload: OlcumIstegi):
    """Ölçümü kuyruğa alır ve iş kimliği döndürür."""
    domain = validate_domain(payload.domain)
    # Çözümleme kapısı BURADA, işi kuyruğa almadan önce uygulanır.
    # `validate_domain` yalnızca biçim bakar: "127.0.0.1.nip.io" ve
    # "localtest.me" o kapıdan geçip loopback'e çözülür. Kontrolü arka plana
    # bırakmak güvenlik açığı olmazdı (motor da doğruluyor) ama teknisyene
    # iş kimliği verip 15 saniye sonra hata göstermek ve kuyruk yeri harcamak
    # anlamına gelirdi.
    await resolve_public_ips_async(domain, 443)

    stratejiler = payload.stratejiler or list(_GECERLI_STRATEJILER)
    stratejiler = [s for s in stratejiler if s in _GECERLI_STRATEJILER]
    if not stratejiler:
        raise HTTPException(400, "Geçerli strateji yok (mobile veya desktop olmalı)")

    _supur()
    if _bekleyen_sayisi() >= _MAX_BEKLEYEN:
        raise HTTPException(
            429, "Şu anda çok fazla ölçüm sırada. Birkaç dakika sonra tekrar deneyin.")

    is_id = uuid.uuid4().hex[:16]
    _ISLER[is_id] = {
        "durum": "kuyrukta", "ilerleme": 0, "adim": "Sıraya alındı…",
        "domain": domain, "hata": None, "sonuc": None,
        "olusturma": time.time(),
    }

    # Görev referansı tutulmalı: aksi hâlde asyncio görevi çöp toplayıcıya
    # kapılıp sessizce iptal olabilir.
    gorev = asyncio.create_task(_calistir(is_id, domain, stratejiler))
    _ISLER[is_id]["_gorev"] = gorev

    return IsYaniti(is_id=is_id)


@router.get("/job/{is_id}", response_model=IsDurumu)
@limiter.limit("180/minute")
async def is_durumu(request: Request, is_id: str):
    """İşin ilerlemesini ve bittiyse sonucunu döndürür."""
    is_kaydi = _ISLER.get(is_id)
    if not is_kaydi:
        raise HTTPException(
            404, "Ölçüm bulunamadı — süresi dolmuş ya da sunucu yeniden başlatılmış olabilir.")

    return IsDurumu(
        is_id=is_id,
        durum=is_kaydi["durum"],
        ilerleme=is_kaydi["ilerleme"],
        adim=is_kaydi["adim"],
        domain=is_kaydi["domain"],
        hata=is_kaydi["hata"],
        sonuc=is_kaydi["sonuc"],
    )


@router.get("/history/{domain}")
@limiter.limit("30/minute")
async def olcum_gecmisi(request: Request, domain: str,
                        strategy: str | None = None,
                        db: Session = Depends(get_db)):
    """Bir alan adının kayıtlı ölçüm geçmişi."""
    temiz = validate_domain(domain)
    if strategy and strategy not in _GECERLI_STRATEJILER:
        raise HTTPException(400, "Strateji mobile veya desktop olmalı")
    return {"domain": temiz, "kayitlar": store.gecmis(db, temiz, strategy, limit=50)}


@router.get("/durum")
@limiter.limit("60/minute")
async def servis_durumu(request: Request):
    """Arayüzün Google katmanının açık olup olmadığını öğrenmesi için."""
    return {
        "google_etkin": google.etkin(),
        "bekleyen_is": _bekleyen_sayisi(),
        "stratejiler": list(_GECERLI_STRATEJILER),
    }
