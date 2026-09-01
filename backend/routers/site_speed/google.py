"""Opsiyonel Google katmanı — PageSpeed Insights + CrUX.

`PAGESPEED_API_KEY` tanımlı değilse bu modülün tüm fonksiyonları `None`
döndürür ve arayüzde ilgili bölümler hiç görünmez. Hata değil, yokluk.

ANAHTAR ZORUNLUDUR. Google, anahtarsız çağrıları paylaşılan bir anonim
projeye yazıyor ve o projenin günlük kotası kalıcı olarak 0:

    {"error":{"code":429,"status":"RESOURCE_EXHAUSTED",
      "details":[{"metadata":{"quota_limit_value":"0"}}]}}

Dokümantasyon hâlâ anahtarı "sık sorgular için önerilir" diye geçiyor;
gerçek bu değil. Anahtarsız kullanım denenmemelidir.

Neden CrUX ayrı bir API'den çağrılıyor: Google, PSI yanıtındaki
`loadingExperience` / `originLoadingExperience` alanlarını kaldıracağını
duyurdu. Saha verisini baştan doğru kaynaktan almak, sonra taşımaktan ucuz.
Ayrıca INP **yalnızca** saha verisinden gelir — lab ölçümü etkileşim
gerektirdiği için üretemez.
"""

import asyncio
import os
import urllib.parse

import httpx

_PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
_CRUX_URL = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"

# PSI ağır sayfalarda 60 sn'yi aşabilir; Google kendi iç sınırını 120 sn yaptı.
_PSI_TIMEOUT = 120.0
_CRUX_TIMEOUT = 20.0

# Lighthouse 13 "Opportunities"i "Insights" ile değiştirdi ve eski audit
# verisini KALDIRDI. Eski id'lerle arayan kod hata vermez — sessizce boş
# liste alır. Bu yüzden her iki kuşağın id'leri de aranıyor.
_FIRSAT_AUDITLERI = (
    # Lighthouse 13 insight'ları
    "render-blocking-insight", "document-latency-insight", "image-delivery-insight",
    "use-cache-insight", "modern-http-insight", "network-dependency-tree-insight",
    "lcp-discovery-insight", "lcp-phases-insight", "cls-culprits-insight",
    "legacy-javascript-insight", "duplicated-javascript-insight",
    "third-parties-insight", "font-display-insight", "dom-size-insight",
    "viewport-insight", "forced-reflow-insight", "inp-breakdown-insight",
    # Lighthouse 12 ve öncesi (eski kurulumlar / önbellekli yanıtlar)
    "render-blocking-resources", "unused-css-rules", "unused-javascript",
    "modern-image-formats", "uses-optimized-images", "uses-text-compression",
    "uses-responsive-images", "efficient-animated-content", "duplicated-javascript",
    "legacy-javascript", "uses-long-cache-ttl", "server-response-time",
    "redirects", "uses-rel-preconnect", "total-byte-weight",
)

# Skoru olmayan denetim modları — `score` bu modlarda None'dır ve
# "başarısız" gibi gösterilmesi klasik bir hatadır.
_SKORSUZ_MODLAR = {"informative", "manual", "notApplicable", "error"}

_CRUX_METRIKLER = [
    "largest_contentful_paint", "interaction_to_next_paint",
    "cumulative_layout_shift", "first_contentful_paint",
    "experimental_time_to_first_byte",
]


def anahtar() -> str:
    return (os.getenv("PAGESPEED_API_KEY") or "").strip()


def etkin() -> bool:
    return bool(anahtar())


def _tasarruf_ms(audit: dict) -> int:
    """Hem yeni (`metricSavings`) hem eski (`overallSavingsMs`) şemayı okur."""
    ms = audit.get("metricSavings") or {}
    yeni = max(ms.get("LCP", 0) or 0, ms.get("FCP", 0) or 0, ms.get("TBT", 0) or 0)
    eski = (audit.get("details") or {}).get("overallSavingsMs", 0) or 0
    return int(yeni or eski)


def _tasarruf_bayt(audit: dict) -> int:
    return int((audit.get("details") or {}).get("overallSavingsBytes", 0) or 0)


def _durum(audit: dict) -> str:
    """Lighthouse audit'ini panelin dört durumlu sözlüğüne çevirir."""
    if audit.get("scoreDisplayMode") in _SKORSUZ_MODLAR:
        return "info"
    skor = audit.get("score")
    if skor is None:
        return "info"
    if skor >= 0.9:
        return "healthy"
    if skor >= 0.5:
        return "warning"
    return "error"


async def psi(domain: str, strategy: str) -> dict | None:
    """PageSpeed Insights resmî sonucu. Anahtar yoksa None."""
    key = anahtar()
    if not key:
        return None

    params = {
        "url": f"https://{domain}/",
        "key": key,
        "strategy": strategy,
        "category": "performance",
        "locale": "tr",          # başlık/açıklamalar Türkçe döner, çeviri gerekmez
    }

    try:
        async with httpx.AsyncClient(timeout=_PSI_TIMEOUT, follow_redirects=False) as c:
            r = await asyncio.wait_for(
                c.get(_PSI_URL, params=params), timeout=_PSI_TIMEOUT)
    except Exception as e:
        return {"hata": f"PSI'ye ulaşılamadı: {type(e).__name__}"}

    if r.status_code != 200:
        try:
            mesaj = (r.json().get("error") or {}).get("message", "")[:200]
        except Exception:
            mesaj = r.text[:200]
        aciklama = {
            400: "Geçersiz istek — adres Google tarafından kabul edilmedi",
            403: "API anahtarı reddedildi (kısıtlama ya da API etkin değil)",
            429: "Google kotası doldu — bir süre sonra tekrar deneyin",
            500: "Google tarafında hata (hedef sayfa yüklenemedi olabilir)",
        }.get(r.status_code, f"HTTP {r.status_code}")
        return {"hata": f"{aciklama}. {mesaj}".strip()}

    data = r.json()
    lhr = data.get("lighthouseResult") or {}

    # HTTP 200 dönse bile Lighthouse çökmüş olabilir; skor None gelir.
    runtime = lhr.get("runtimeError")
    if runtime and runtime.get("code"):
        return {"hata": f"Lighthouse hedefi ölçemedi: {runtime.get('message', runtime['code'])[:200]}"}

    kategoriler = lhr.get("categories") or {}
    perf = (kategoriler.get("performance") or {}).get("score")
    audits = lhr.get("audits") or {}

    def metrik(aid: str):
        return (audits.get(aid) or {}).get("numericValue")

    firsatlar = []
    for aid in _FIRSAT_AUDITLERI:
        a = audits.get(aid)
        if not a:
            continue
        durum = _durum(a)
        if durum in ("healthy", "info"):
            continue
        firsatlar.append({
            "id": aid,
            "baslik": a.get("title", aid),
            "aciklama": (a.get("description") or "")[:600],
            "durum": durum,
            "deger": a.get("displayValue") or "",
            "tasarruf_ms": _tasarruf_ms(a),
            "tasarruf_bayt": _tasarruf_bayt(a),
            "oncelik": a.get("guidanceLevel") or 3,
        })
    # Google'ın kendi sıralaması: önce rehberlik seviyesi, sonra kazanç
    firsatlar.sort(key=lambda f: (f["oncelik"], -f["tasarruf_ms"], -f["tasarruf_bayt"]))

    ekran = ((audits.get("final-screenshot") or {}).get("details") or {}).get("data")

    return {
        "skor": round(perf * 100) if perf is not None else None,
        "lighthouse_surumu": lhr.get("lighthouseVersion"),
        "olcum_zamani": data.get("analysisUTCTimestamp"),
        "kanonik_url": data.get("id"),
        "metrikler": {
            "fcp_ms": metrik("first-contentful-paint"),
            "si_ms":  metrik("speed-index"),
            "lcp_ms": metrik("largest-contentful-paint"),
            "tbt_ms": metrik("total-blocking-time"),
            "cls":    metrik("cumulative-layout-shift"),
        },
        "firsatlar": firsatlar[:20],
        "ekran_goruntusu": ekran,
    }


def _crux_kayit(record: dict) -> dict:
    metrikler = record.get("metrics") or {}

    def p75(ad):
        m = metrikler.get(ad)
        if not m:
            return None
        # CrUX API'de p75 doğru ondalıkla gelir (PSI'daki ×100 tuhaflığı yok)
        return (m.get("percentiles") or {}).get("p75")

    def dagilim(ad):
        m = metrikler.get(ad)
        if not m:
            return []
        return [{"baslangic": h.get("start"), "bitis": h.get("end"),
                 "oran": h.get("density", 0)}
                for h in (m.get("histogram") or [])]

    return {
        "lcp_ms":  p75("largest_contentful_paint"),
        "inp_ms":  p75("interaction_to_next_paint"),
        "cls":     p75("cumulative_layout_shift"),
        "fcp_ms":  p75("first_contentful_paint"),
        "ttfb_ms": p75("experimental_time_to_first_byte"),
        "dagilim": {
            "lcp": dagilim("largest_contentful_paint"),
            "inp": dagilim("interaction_to_next_paint"),
            "cls": dagilim("cumulative_layout_shift"),
        },
        "donem": record.get("collectionPeriod") or {},
    }


async def crux(domain: str, strategy: str) -> dict | None:
    """CrUX saha verisi. Önce tam URL, veri yoksa origin geneline düşer.

    Bu ayrım kullanıcıya gösterilmelidir: origin verisi anasayfa ağırlıklıdır,
    "bu sayfanın LCP'si" sanılan sayı aslında site ortalaması olabilir.
    """
    key = anahtar()
    if not key:
        return None

    form = "PHONE" if strategy == "mobile" else "DESKTOP"
    hedefler = [
        ("url", f"https://{domain}/", "Bu URL"),
        ("origin", f"https://{domain}", "Origin geneli"),
    ]

    async with httpx.AsyncClient(timeout=_CRUX_TIMEOUT, follow_redirects=False) as c:
        for alan, deger, etiket in hedefler:
            govde = {alan: deger, "formFactor": form, "metrics": _CRUX_METRIKLER}
            try:
                r = await asyncio.wait_for(
                    c.post(_CRUX_URL, params={"key": key}, json=govde),
                    timeout=_CRUX_TIMEOUT)
            except Exception:
                return None

            if r.status_code == 404:
                # Yeterli örneklem yok — hata değil, normal durum. Origin'e düş.
                continue
            if r.status_code != 200:
                return None

            kayit = (r.json() or {}).get("record")
            if not kayit:
                continue
            sonuc = _crux_kayit(kayit)
            sonuc["kapsam"] = etiket
            sonuc["kapsam_url"] = deger
            return sonuc

    return {"kapsam": None, "veri_yok": True}
