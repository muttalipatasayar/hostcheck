"""Playwright tabanlı performans ölçüm motoru.

`screenshot.py`'nin kanıtlanmış desenini izler: Playwright'ın **sync** API'si
kendi ThreadPoolExecutor'ında çalışır, çünkü `sync_playwright` üzerinde
çalışan bir event loop bulunmayan bir thread ister. FastAPI tek event loop
üstünde döndüğü için bloklayan çağrı doğrudan yapılırsa tüm panel donar.

Havuz `max_workers=1`: systemd biriminde `MemoryMax` sınırlı ve screenshot
aracının kendi 2 worker'lık havuzu zaten var. Üçüncü bir Chromium'un aynı
anda ayağa kalkması OOM riski demek.

SSRF: hedef önce `validate_domain` (format) sonra `resolve_public_ips_async`
(çözümleme) kapısından geçer, Chromium ana hostu doğrulanmış IP'ye pinlenir
ve HER alt istek `make_playwright_route_guard` ile süzülür.
"""

import asyncio
import concurrent.futures
import os
import pathlib
import urllib.parse

from dns_core import kayit_alan_adi
from net_validation import make_playwright_route_guard, resolve_public_ips_async

_HERE = pathlib.Path(__file__).parent
_WEB_VITALS = (_HERE / "vendor" / "web-vitals.attribution.iife.js").read_text(encoding="utf-8")
_COLLECTOR = (_HERE / "collector.js").read_text(encoding="utf-8")
# Kütüphane önce, gözlemciler sonra — collector `webVitals` global'ine bağımlı
_INIT_SCRIPT = _WEB_VITALS + "\n" + _COLLECTOR

# Ölçüm başına tek tarayıcı; screenshot havuzundan ayrı tutulur ki iki araç
# birbirinin sırasını yemesin.
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="sitespeed")
# Executor zaten seri çalıştırır; semafor kuyruğun event loop tarafında
# görünür olmasını ve iş sınırının uygulanabilmesini sağlar.
_SEMAPHORE = asyncio.Semaphore(1)

_NAV_TIMEOUT = 45000        # ms — ağ kısıtlaması altında yükleme uzun sürer
_IDLE_TIMEOUT = 8000        # ms — networkidle beklemesi (başarısız olabilir)
_SETTLE_MS = 2500           # geç gelen LCP adayları için ek bekleme
_RUN_TIMEOUT = 110.0        # sn — motorun tamamı için duvar saati sınırı

_UA_MOBILE = ("Mozilla/5.0 (Linux; Android 11; moto g power (2022)) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 "
              "Mobile Safari/537.36")
_UA_DESKTOP = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Lighthouse `core/config/constants.js` içindeki uygulanan-kısıtlama profilleri.
# Sayıları değiştirmek skoru doğrudan kaydırır; PSI ile kıyaslanabilirlik
# bu değerlere bağlı.
DEVICES = {
    "mobile": {
        "viewport": {"width": 412, "height": 823},
        "dpr": 1.75,
        "mobil": True,
        "ua": _UA_MOBILE,
        "cpu_kisidi": 4,                      # mobileSlow4G: cpuSlowdownMultiplier
        "ag": {                               # mobileSlow4G, DevTools kısıtlaması
            "offline": False,
            "latency": 150 * 3.75,            # requestLatencyMs
            "downloadThroughput": int(1.6 * 1024 * 0.9 * 1024 / 8),
            "uploadThroughput": int(750 * 0.9 * 1024 / 8),
        },
    },
    "desktop": {
        "viewport": {"width": 1350, "height": 940},
        "dpr": 1.0,
        "mobil": False,
        "ua": _UA_DESKTOP,
        "cpu_kisidi": 1,                      # desktopDense4G: CPU kısıtlaması yok
        # Lighthouse masaüstünde DevTools kısıtlaması uygulamaz; yavaşlatmayı
        # lantern ile SİMÜLE eder. Biz simüle edemediğimiz için desktopDense4G
        # hedeflerini (40 ms RTT / 10 Mbps) doğrudan uyguluyoruz. Kısıtlamayı
        # tamamen kapatmak, sunucunun veri merkezi bağlantısını ölçmek olurdu —
        # masaüstü skorları gerçekçi olmayacak kadar yüksek çıkardı.
        "ag": {
            "offline": False,
            "latency": 40,
            "downloadThroughput": int(10 * 1024 * 1024 / 8),
            "uploadThroughput": int(10 * 1024 * 1024 / 8),
        },
    },
}

# Bir kaynağın kaç bayt olduğunu bilmeden şelale çizilemez; ama bu sınır
# aşılırsa yanıt devasa olur. En büyük N kaynak arayüze taşınır.
_MAX_KAYNAK = 200


# Sayfa yüklendikten sonra tek seferde okunan DOM + zamanlama verisi.
_PAGE_PROBE = """
() => {
  const nav = performance.getEntriesByType('navigation')[0] || null;
  const res = performance.getEntriesByType('resource').map(r => ({
    url: r.name,
    tip: r.initiatorType,
    protokol: r.nextHopProtocol || '',
    baslangic: Math.round(r.startTime),
    sure: Math.round(r.duration),
    dns: Math.round(r.domainLookupEnd - r.domainLookupStart),
    tcp: Math.round(r.connectEnd - r.connectStart),
    ttfb: Math.round(r.responseStart - r.requestStart),
    transferSize: r.transferSize || 0,
    encodedBodySize: r.encodedBodySize || 0,
    decodedBodySize: r.decodedBodySize || 0,
  }));

  // Render engelleyen kaynaklar: <head> içindeki senkron script ve
  // media sorgusu olmayan stylesheet'ler.
  const engelleyen = [];
  document.querySelectorAll('head script[src]').forEach(s => {
    if (!s.async && !s.defer && s.type !== 'module')
      engelleyen.push({ url: s.src, tur: 'script' });
  });
  document.querySelectorAll('head link[rel="stylesheet"]').forEach(l => {
    const m = l.media;
    if (!m || m === 'all' || m === 'screen')
      engelleyen.push({ url: l.href, tur: 'stylesheet' });
  });

  // Görseller: doğal boyut vs ekranda kapladığı yer, format, lazy-load
  const gorseller = [];
  document.querySelectorAll('img').forEach(img => {
    const rect = img.getBoundingClientRect();
    gorseller.push({
      url: img.currentSrc || img.src || '',
      dogal_g: img.naturalWidth || 0,
      dogal_y: img.naturalHeight || 0,
      goruntu_g: Math.round(rect.width),
      goruntu_y: Math.round(rect.height),
      lazy: img.loading === 'lazy',
      ekranda: rect.top < window.innerHeight && rect.bottom > 0,
    });
  });

  return {
    nav: nav ? {
      dns: Math.round(nav.domainLookupEnd - nav.domainLookupStart),
      tcp: Math.round(nav.connectEnd - nav.connectStart),
      tls: nav.secureConnectionStart > 0
             ? Math.round(nav.connectEnd - nav.secureConnectionStart) : 0,
      ttfb: Math.round(nav.responseStart - nav.requestStart),
      indirme: Math.round(nav.responseEnd - nav.responseStart),
      dom_interaktif: Math.round(nav.domInteractive),
      dom_hazir: Math.round(nav.domContentLoadedEventEnd),
      yuklendi: Math.round(nav.loadEventEnd),
      protokol: nav.nextHopProtocol || '',
      encodedBodySize: nav.encodedBodySize || 0,
      decodedBodySize: nav.decodedBodySize || 0,
    } : null,
    kaynaklar: res,
    engelleyen: engelleyen,
    gorseller: gorseller,
    dom_dugum_sayisi: document.getElementsByTagName('*').length,
    baslik: document.title || '',
    hc: window.__hc || null,
  };
}
"""


def _sync_olc(url: str, host: str, ip: str, strategy: str) -> dict:
    """Playwright ölçümü — kendi thread'inde, kendi event loop'unda çalışır."""
    from playwright.sync_api import sync_playwright

    cihaz = DEVICES[strategy]

    # Varsayılan "production": .env okunamazsa sandbox AÇIK kalmalı.
    extra = ["--no-sandbox"] if os.getenv("ENV", "production") == "development" else []
    args = extra + [
        "--disable-dev-shm-usage",
        "--disable-gpu",
        # Ana hostu doğrulanmış IP'ye pinle → doğrulama ile gezinme arasındaki
        # DNS rebinding penceresi kapanır. EXCLUDE'lar yerel isimleri de keser.
        f"--host-resolver-rules=MAP {host} {ip},EXCLUDE localhost,EXCLUDE *.local",
    ]

    # CDP'den toplanan gerçek tel boyutları: response.body() decode edilmiş
    # gövdeyi verir, gzip/brotli sonrası tel üzerindeki baytı değil.
    tel_boyut: dict[str, int] = {}
    istek_bilgi: dict[str, dict] = {}
    basarisiz: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=args)
        try:
            context = browser.new_context(
                viewport=cihaz["viewport"],
                device_scale_factor=cihaz["dpr"],
                is_mobile=cihaz["mobil"],
                has_touch=cihaz["mobil"],
                user_agent=cihaz["ua"],
                ignore_https_errors=True,
            )
            page = context.new_page()

            # SSRF kapısı — her alt istek doğrulanır (paylaşılan primitif)
            page.route("**/*", make_playwright_route_guard())

            # Ölçüm scripti navigasyondan ÖNCE kurulmalı; sonra enjekte
            # edilirse LCP/CLS gözlemcileri ilk boyamaları kaçırır.
            page.add_init_script(_INIT_SCRIPT)

            cdp = context.new_cdp_session(page)
            cdp.send("Network.enable")

            def _on_response(e):
                r = e.get("response") or {}
                istek_bilgi[e["requestId"]] = {
                    "url": r.get("url", ""),
                    "status": r.get("status", 0),
                    "mime": r.get("mimeType", ""),
                    "protokol": r.get("protocol", ""),
                    "basliklar": {k.lower(): v for k, v in (r.get("headers") or {}).items()},
                    "onbellekten": bool(r.get("fromDiskCache") or r.get("fromPrefetchCache")),
                }

            def _on_finished(e):
                tel_boyut[e["requestId"]] = int(e.get("encodedDataLength") or 0)

            def _on_failed(e):
                bilgi = istek_bilgi.get(e["requestId"], {})
                if len(basarisiz) < 50:
                    basarisiz.append({
                        "url": bilgi.get("url", ""),
                        "sebep": e.get("errorText", ""),
                        "status": bilgi.get("status", 0),
                    })

            cdp.on("Network.responseReceived", _on_response)
            cdp.on("Network.loadingFinished", _on_finished)
            cdp.on("Network.loadingFailed", _on_failed)

            # CPU ve ağ kısıtlaması — emülasyon olmadan sonuçlar gerçekçi
            # olmayacak kadar iyi çıkar (sunucu fiber hatta, CPU serbest).
            if cihaz["cpu_kisidi"] > 1:
                cdp.send("Emulation.setCPUThrottlingRate",
                         {"rate": cihaz["cpu_kisidi"]})
            if cihaz["ag"]:
                cdp.send("Network.emulateNetworkConditions", cihaz["ag"])

            page.goto(url, timeout=_NAV_TIMEOUT, wait_until="domcontentloaded")

            # networkidle çoğu sitede hiç gelmez (analytics uzun-yoklama yapar);
            # başarısızlığı ölçümü iptal etmemeli.
            try:
                page.wait_for_load_state("networkidle", timeout=_IDLE_TIMEOUT)
            except Exception:
                pass

            page.wait_for_timeout(_SETTLE_MS)

            # LCP sayfa görünürlüğü sonlanana kadar kesinleşmez. web-vitals
            # bu olayı dinler; tetiklemezsek son LCP adayı raporlanmaz.
            try:
                page.evaluate(
                    "() => { Object.defineProperty(document,'visibilityState',"
                    "{value:'hidden',configurable:true});"
                    "document.dispatchEvent(new Event('visibilitychange')); }")
                page.wait_for_timeout(300)
            except Exception:
                pass

            sonuc = page.evaluate(_PAGE_PROBE)

            try:
                ss = page.screenshot(type="jpeg", quality=62, full_page=False)
            except Exception:
                ss = b""

            son_url = page.url
        finally:
            browser.close()

    # CDP verisini url anahtarlı sözlüğe indir
    tel: dict[str, dict] = {}
    for rid, bilgi in istek_bilgi.items():
        u = bilgi.get("url") or ""
        if not u:
            continue
        tel[u] = {**bilgi, "tel_bayt": tel_boyut.get(rid, 0)}

    sonuc["tel"] = tel
    sonuc["basarisiz"] = basarisiz
    sonuc["ekran_goruntusu"] = ss
    sonuc["son_url"] = son_url
    return sonuc


def _tbt_hesapla(long_tasks: list, fcp_ms: float | None) -> float:
    """Total Blocking Time — FCP sonrası 50 ms'yi aşan görevlerin aşan kısmı."""
    if not long_tasks:
        return 0.0
    esik = fcp_ms or 0
    toplam = 0.0
    for t in long_tasks:
        baslangic = t.get("baslangic", 0)
        sure = t.get("sure", 0)
        if baslangic + sure <= esik:
            continue
        # Görev FCP'yi kesiyorsa yalnızca sonrasındaki kısmı say
        etkin = sure - max(0.0, esik - baslangic)
        toplam += max(0.0, etkin - 50)
    return round(toplam, 1)


async def olc(domain: str, strategy: str) -> dict:
    """Bir alan adını verilen strateji için ölçer.

    Çağıranın `validate_domain` ile format kapısını geçmiş olması beklenir;
    çözümleme kapısı burada uygulanır.
    """
    ip = (await resolve_public_ips_async(domain, 443))[0]
    loop = asyncio.get_event_loop()

    async with _SEMAPHORE:
        son_hata = "Bilinmeyen hata"
        for scheme in ("https", "http"):
            try:
                ham = await asyncio.wait_for(
                    loop.run_in_executor(
                        _EXECUTOR, _sync_olc, f"{scheme}://{domain}/", domain, ip, strategy),
                    timeout=_RUN_TIMEOUT,
                )
                return _normalize(ham, domain, strategy)
            except asyncio.TimeoutError:
                son_hata = f"Ölçüm zaman aşımına uğradı ({int(_RUN_TIMEOUT)} sn)"
            except Exception as e:
                son_hata = f"{type(e).__name__}: {str(e)[:200]}" if str(e) else type(e).__name__

    raise RuntimeError(son_hata)


def _normalize(ham: dict, domain: str, strategy: str) -> dict:
    """Ham tarayıcı çıktısını arayüzün beklediği şekle sokar."""
    hc = ham.get("hc") or {}
    nav = ham.get("nav") or {}
    tel = ham.get("tel") or {}

    # web-vitals LCP'yi bazı sitelerde hiç raporlamıyor; ham gözlemci yedeği
    # sayıyı kurtarır (attribution alanları o durumda boş kalır).
    lcp = (hc.get("lcp") or {}) if hc else {}
    if not lcp.get("deger") and hc.get("lcpHam"):
        ham_lcp = hc["lcpHam"]
        lcp = {
            "deger": ham_lcp.get("deger"),
            "element": ham_lcp.get("element"),
            "url": ham_lcp.get("url"),
            "ttfb_ms": 0, "kaynak_gecikmesi_ms": 0,
            "kaynak_suresi_ms": 0, "render_gecikmesi_ms": 0,
            "yedek": True,
        }
    cls = (hc.get("cls") or {}) if hc else {}
    fcp = (hc.get("fcp") or {}) if hc else {}
    ttfb = (hc.get("ttfb") or {}) if hc else {}

    fcp_ms = fcp.get("deger")
    tbt_ms = _tbt_hesapla((hc.get("longTasks") or []), fcp_ms)

    # Kaynakları tel boyutuyla zenginleştir; tel bilgisi yoksa Resource
    # Timing'in transferSize'ına düş (cross-origin'de 0 gelebilir).
    kaynaklar = []
    ana_alan = kayit_alan_adi(domain)
    for r in (ham.get("kaynaklar") or []):
        url = r.get("url") or ""
        t = tel.get(url, {})
        bayt = t.get("tel_bayt") or r.get("transferSize") or 0
        host = urllib.parse.urlparse(url).hostname or ""
        kaynaklar.append({
            **r,
            "tel_bayt": bayt,
            "host": host,
            "ucuncu_taraf": bool(host) and kayit_alan_adi(host) != ana_alan,
            "status": t.get("status", 0),
            "mime": t.get("mime", ""),
            "basliklar": t.get("basliklar", {}),
            "protokol": t.get("protokol") or r.get("protokol") or "",
        })

    # Şelale için en uzun/en büyük kaynaklar önde olsun; arayüz zaten sınırlı
    # sayıda satır gösteriyor.
    kaynaklar.sort(key=lambda k: k.get("baslangic", 0))

    return {
        "strateji": strategy,
        "son_url": ham.get("son_url", ""),
        "baslik": ham.get("baslik", ""),
        "metrikler": {
            "fcp_ms":  round(fcp_ms, 1) if fcp_ms is not None else None,
            "lcp_ms":  round(lcp["deger"], 1) if lcp.get("deger") is not None else None,
            "cls":     round(cls["deger"], 4) if cls.get("deger") is not None else None,
            "tbt_ms":  tbt_ms,
            "ttfb_ms": round(ttfb["deger"], 1) if ttfb.get("deger") is not None else None,
        },
        "lcp_detay": lcp or None,
        "cls_detay": cls or None,
        "ttfb_detay": ttfb or None,
        "navigasyon": nav,
        "kaynaklar": kaynaklar[:_MAX_KAYNAK],
        "kaynak_sayisi": len(kaynaklar),
        "engelleyen": ham.get("engelleyen") or [],
        "gorseller": ham.get("gorseller") or [],
        "dom_dugum_sayisi": ham.get("dom_dugum_sayisi", 0),
        "basarisiz": ham.get("basarisiz") or [],
        "konsol_hatalari": (hc.get("konsolHatalari") or []) if hc else [],
        "ekran_goruntusu": ham.get("ekran_goruntusu") or b"",
    }
