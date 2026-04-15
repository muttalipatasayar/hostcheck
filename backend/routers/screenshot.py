import asyncio
import concurrent.futures
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from rate_limiter import limiter
from routers.quick_check import validate_domain

router = APIRouter(prefix="/api/screenshot", tags=["screenshot"])

# Bellek içi cache: domain → (zaman damgası, png bytes)
_CACHE: dict[str, tuple[float, bytes]] = {}
_CACHE_TTL = 300  # 5 dakika

# Playwright için ayrı thread pool — FastAPI event loop ile çakışmasın
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="playwright")


def _sync_screenshot(url: str) -> bytes:
    """Kendi asyncio event loop'unu oluşturan thread'de çalışır."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # Önce sisteme kurulu Edge'i dene, yoksa Chromium kullan
        browser = None
        # --no-sandbox Chromium sandbox güvenliğini devre dışı bırakır;
        # yalnızca geliştirme ortamında veya Docker içinde gereklidir.
        import os as _os
        _extra = ["--no-sandbox"] if _os.getenv("ENV", "development") == "development" else []
        _base_args = _extra + ["--disable-dev-shm-usage", "--disable-gpu"]

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

            page.goto(url, timeout=12000, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)  # JS render için 1 sn bekle
            screenshot = page.screenshot(type="png", full_page=False)
            return screenshot
        finally:
            browser.close()


@router.get("/{domain:path}")
@limiter.limit("15/minute")
async def get_screenshot(request: Request, domain: str):
    # SSRF koruması — geçersiz/dahili domain'leri reddet
    domain = validate_domain(domain)

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
                loop.run_in_executor(_EXECUTOR, _sync_screenshot, f"{scheme}://{domain}"),
                timeout=20.0,
            )
            _CACHE[domain] = (time.time(), data)
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
