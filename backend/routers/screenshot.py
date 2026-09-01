import asyncio
import concurrent.futures
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from net_validation import make_playwright_route_guard, resolve_public_ips_async
from rate_limiter import limiter
from routers.quick_check import validate_domain

router = APIRouter(prefix="/api/screenshot", tags=["screenshot"])

# Bellek içi cache: domain → (zaman damgası, png bytes)
# Üst sınır ŞART: her farklı domain kalıcı olarak bir PNG ekliyordu ve süresi
# dolan girdi hiç silinmiyordu (yalnızca okuma anında atlanıyordu) — wildcard
# DNS ile sonsuz benzersiz isim üretmek bedava olduğundan bu, auth'suz bir
# bellek tüketme vektörüydü.
_CACHE: dict[str, tuple[float, bytes]] = {}
_CACHE_TTL = 300      # 5 dakika
_CACHE_MAX_ENTRIES = 64
_CACHE_MAX_BYTES = 64 * 1024 * 1024


def _cache_store(domain: str, data: bytes) -> None:
    """Süresi dolanları temizler, sonra sınırları aşan en eski girdileri atar."""
    now = time.time()
    for key in [k for k, (ts, _) in _CACHE.items() if now - ts >= _CACHE_TTL]:
        _CACHE.pop(key, None)

    _CACHE.pop(domain, None)          # yeniden ekleyerek en yeniye taşı
    _CACHE[domain] = (now, data)

    total = sum(len(v) for _, v in _CACHE.values())
    while _CACHE and (len(_CACHE) > _CACHE_MAX_ENTRIES or total > _CACHE_MAX_BYTES):
        oldest = next(iter(_CACHE))   # dict ekleme sırasını korur → FIFO
        total -= len(_CACHE[oldest][1])
        _CACHE.pop(oldest, None)

# Playwright için ayrı thread pool — FastAPI event loop ile çakışmasın
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="playwright")


def _sync_screenshot(url: str, pinned_host: str = "", pinned_ip: str = "") -> bytes:
    """Kendi asyncio event loop'unu oluşturan thread'de çalışır."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # Önce sisteme kurulu Edge'i dene, yoksa Chromium kullan
        browser = None
        # --no-sandbox Chromium sandbox güvenliğini devre dışı bırakır;
        # yalnızca geliştirme ortamında veya Docker içinde gereklidir.
        import os as _os
        # Varsayılan "production": ENV okunamazsa sandbox AÇIK kalmalı.
        # Eskiden varsayılan "development"ti; .env okunamadığında üretim
        # sunucusu sessizce sandbox'sız Chromium başlatıyordu ve render
        # edilen sayfayı auth'suz bir uçtan saldırgan seçiyordu.
        _extra = ["--no-sandbox"] if _os.getenv("ENV", "production") == "development" else []
        _base_args = _extra + ["--disable-dev-shm-usage", "--disable-gpu"]

        # Ana hostu doğrulanmış IP'ye pinle → doğrulama ile gezinme arasındaki
        # DNS rebinding penceresi kapanır. EXCLUDE'lar yerel isimlerin
        # çözülmesini de engeller.
        if pinned_host and pinned_ip:
            _base_args.append(
                f"--host-resolver-rules=MAP {pinned_host} {pinned_ip},"
                "EXCLUDE localhost,EXCLUDE *.local"
            )

        for launch_opts in [
            {"channel": "msedge", "headless": True},
            {"headless": True},
        ]:
            try:
                browser = p.chromium.launch(
                    **launch_opts,
                    args=_base_args,
                )
                break
            except Exception:
                continue

        if browser is None:
            raise RuntimeError("Tarayıcı başlatılamadı")

        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
                ),
            )
            page = context.new_page()

            # Font dosyalarını blokla — hız için
            page.route("**/*.{woff,woff2,ttf,otf}", lambda r: r.abort())
            # SSRF kapısı: iç adrese giden her isteği iptal et
            page.route("**/*", make_playwright_route_guard())

            page.goto(url, timeout=12000, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)  # JS render için 1 sn bekle
            screenshot = page.screenshot(type="png", full_page=False)
            return screenshot
        finally:
            browser.close()


@router.get("/{domain:path}")
@limiter.limit("15/minute")
async def get_screenshot(request: Request, domain: str):
    # SSRF koruması — iki aşamalı:
    #  1) format/IP-literal doğrulaması (string)
    #  2) ÇÖZÜMLEME doğrulaması — "127.0.0.1.nip.io" gibi isimler 1. aşamayı
    #     geçip 127.0.0.1'e çözülüyordu; tarayıcı iç servisi render edip PNG
    #     olarak geri döndürüyordu.
    domain = validate_domain(domain)
    pinned_ip = (await resolve_public_ips_async(domain, 443))[0]

    # Cache'den dön
    cached = _CACHE.get(domain)
    if cached:
        ts, data = cached
        if time.time() - ts < _CACHE_TTL:
            return Response(
                content=data,
                media_type="image/png",
                headers={"X-Cache": "HIT"},
            )

    loop = asyncio.get_event_loop()
    last_err = "Bilinmeyen hata"

    for scheme in ("https", "http"):
        try:
            data = await asyncio.wait_for(
                loop.run_in_executor(
                    _EXECUTOR, _sync_screenshot, f"{scheme}://{domain}", domain, pinned_ip
                ),
                timeout=20.0,
            )
            _cache_store(domain, data)
            return Response(
                content=data,
                media_type="image/png",
                headers={"X-Cache": "MISS"},
            )
        except asyncio.TimeoutError:
            last_err = "Zaman aşımı (20s)"
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:100]}" if str(e) else type(e).__name__

    raise HTTPException(status_code=500, detail=f"Screenshot alınamadı: {last_err}")
