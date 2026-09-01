import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# .env, router'lardan ÖNCE yüklenmeli: modül seviyesinde `os.getenv` okuyan
# her router (screenshot, site_speed, ftp, auth_core) aksi hâlde geliştirmede
# .env'i hiç görmez ve üretim varsayılanlarına düşerdi.
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from db_migrate import run_migrations
from rate_limiter import limiter
from routers import quick_check, screenshot, ssl_tools, dns_toolbox, dns_history, dns_propagation, blacklist, mail_health, ssh, rdp, ip_lookup, hazir_yanitlar
from routers import genel_bakis
from routers import site_speed
from routers import ftp as ftp_router
from routers import admin
from routers import uyelik, yonetim

logger = logging.getLogger(__name__)

# Şemayı Alembic ile en güncel sürüme getir
run_migrations()


@asynccontextmanager
async def _yasam_dongusu(_app: FastAPI):
    """Hazır yanıt havuzunu açılışta tohumla.

    Eskiden tohumlama `GET /api/hazir-yanitlar` içinde yapılıyordu; o uç artık
    üyelik istiyor. Orada kalsaydı ilk üye giriş yapana kadar tablo boş kalır,
    yönetim panelindeki istatistikler sıfır gösterirdi.

    Import değil LIFESPAN aşamasında: `import main` tek başına veritabanına
    yazmasın (testler bunu yapıyor). Ayrıca sarmalanmış — bozuk seed JSON'u
    ya da dolu disk DNS/SSL dahil TÜM paneli düşürmemeli.
    """
    from database import SessionLocal

    db = SessionLocal()
    try:
        hazir_yanitlar.seed_if_empty(db)
    except Exception:
        logger.exception("Hazır yanıt tohumlaması başarısız — panel yine de açılıyor.")
    finally:
        db.close()
    yield


app = FastAPI(
    lifespan=_yasam_dongusu,
    title="HostCheck API",
    description="Hosting Destek Otomasyon Paneli",
    version="1.0.0",
    # Üretimde /docs ve /redoc'u kapat
    # Varsayılan "production": .env okunamazsa /docs KAPALI kalmalı.
    # Eskiden varsayılan "development"ti — dosya bozulduğunda üretim sunucusu
    # tüm uç şemasını sessizce ifşa ediyordu. (CLAUDE.md "Ortam bayrağı")
    docs_url="/docs" if os.getenv("ENV", "production") == "development" else None,
    redoc_url=None,
    # /openapi.json `docs_url=None` iken bile AÇIK kalır ve tüm uç şemasını
    # (artık üyelik ve yönetim uçlarını da) anonim olarak servis eder.
    # Üretimde kapatılıyor.
    openapi_url="/openapi.json" if os.getenv("ENV", "production") == "development" else None,
)

# ── Güvenlik başlıkları middleware ────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # API yanıtları önbelleğe ALINMAMALI. Panel Cloudflare arkasında ve
        # zone'da bir "Cache Everything" kuralı olsaydı bir üyenin hazır yanıt
        # kütüphanesi anonim bir ziyaretçiye servis edilebilirdi. `Vary: Cookie`
        # ara önbellekleri de oturuma göre ayırır.
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Vary"] = "Cookie"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        # "1; mode=block" ARTIK ZARARLIDIR: tarayıcıların XSS Auditor'ı
        # kaldırıldı, kalan uygulamalarda bu değer yan kanal açıyor.
        # Gerçek korumayı aşağıdaki CSP sağlıyor.
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # HSTS — tarayıcıyı HTTPS'e zorla (1 yıl)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # CSP — XSS saldırılarını sınırla
        # 'unsafe-eval' KALDIRILDI: üretim build'inde eval()/new Function
        # kullanımı sıfır ölçüldü, yalnızca XSS istismarını kolaylaştırıyordu.
        # 'unsafe-inline' Vite'ın index.html'e gömdüğü modül yükleyici için
        # şimdilik kaldı; nonce'a geçirilirse o da çıkarılabilir.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: blob: https:; "
            "connect-src 'self' ws: wss:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none';"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ── Rate limiter ──────────────────────────────────────────────────────────────

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS — izin verilen originler .env'den okunur ─────────────────────────────

_default_origins = "http://localhost:5173,http://localhost:3000"
allowed_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    # X-CSRF-Token: üyelik uçlarının çift-gönderim CSRF başlığı. Üretimde
    # panel ve API aynı origin'de olduğu için preflight hiç çıkmaz; burada
    # olması yalnızca farklı bir origin'den geliştirme yapılabilmesi içindir.
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
)

app.include_router(quick_check.router)
app.include_router(screenshot.router)
app.include_router(genel_bakis.router)
app.include_router(site_speed.router)
app.include_router(ssl_tools.router)
app.include_router(dns_toolbox.router)
app.include_router(dns_history.router)
app.include_router(dns_propagation.router)
app.include_router(blacklist.router)
app.include_router(mail_health.router)
app.include_router(ftp_router.router)
app.include_router(admin.router)
app.include_router(ssh.router)
app.include_router(rdp.router)
app.include_router(ip_lookup.router)
app.include_router(hazir_yanitlar.router)
app.include_router(uyelik.router)
app.include_router(yonetim.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "HostCheck API"}


@app.get("/")
def root():
    return {"message": "HostCheck API v1.0 — /docs adresine gidin"}
