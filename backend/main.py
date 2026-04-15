import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

from database import engine, Base
from rate_limiter import limiter
from routers import tickets, checks, ai, quick_check, screenshot, ssl_tools, dns_toolbox, dns_history, ssh, rdp, ip_lookup, hazir_yanitlar

load_dotenv()

# Tabloları oluştur
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="HostCheck API",
    description="Hosting Destek Otomasyon Paneli",
    version="1.0.0",
    # Üretimde /docs ve /redoc'u kapat
    docs_url="/docs" if os.getenv("ENV", "development") == "development" else None,
    redoc_url=None,
)

# ── Güvenlik başlıkları middleware ────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # HSTS — tarayıcıyı HTTPS'e zorla (1 yıl)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # CSP — XSS saldırılarını sınırla
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: blob: https:; "
            "connect-src 'self' ws: wss:; "
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
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(tickets.router)
app.include_router(checks.router)
app.include_router(ai.router)
app.include_router(quick_check.router)
app.include_router(screenshot.router)
app.include_router(ssl_tools.router)
app.include_router(dns_toolbox.router)
app.include_router(dns_history.router)
app.include_router(ssh.router)
app.include_router(rdp.router)
app.include_router(ip_lookup.router)
app.include_router(hazir_yanitlar.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "HostCheck API"}


@app.get("/")
def root():
    return {"message": "HostCheck API v1.0 — /docs adresine gidin"}
