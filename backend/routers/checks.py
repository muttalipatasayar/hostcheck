import asyncio
import re
import socket
import ssl
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from schemas import CheckRequest, CheckResponse, CheckResult
from rate_limiter import limiter

try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False

router = APIRouter(prefix="/api/checks", tags=["checks"])

# Public DNS — sistem resolver'ını bypass et
_PUBLIC_DNS = ['8.8.8.8', '1.1.1.1']
_DNS_TIMEOUT = 5.0
_DOMAIN_RE = re.compile(r'^([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$')


def _make_resolver() -> 'dns.resolver.Resolver':
    r = dns.resolver.Resolver(configure=False)
    r.nameservers = _PUBLIC_DNS
    r.timeout = _DNS_TIMEOUT
    r.lifetime = _DNS_TIMEOUT
    return r


def _validate_domain(domain: str) -> str:
    domain = domain.strip().lower()
    domain = re.sub(r'^https?://', '', domain)
    domain = domain.split('/')[0].split('?')[0]
    if not domain or len(domain) > 253:
        raise HTTPException(status_code=400, detail="Geçersiz domain")
    if not _DOMAIN_RE.match(domain):
        raise HTTPException(status_code=400, detail="Geçersiz domain formatı")
    return domain


async def check_dns(domain: str) -> CheckResult:
    if not domain:
        return CheckResult(check_type="DNS", status="skipped", message="Domain belirtilmedi")

    start = time.monotonic()
    try:
        if DNS_AVAILABLE:
            resolver = _make_resolver()
            loop = asyncio.get_event_loop()
            answers = await loop.run_in_executor(None, lambda: resolver.resolve(domain, 'A'))
            ips = [str(r) for r in answers]
            latency = (time.monotonic() - start) * 1000
            return CheckResult(
                check_type="DNS",
                status="healthy",
                value=", ".join(ips),
                message=f"DNS çözümlendi → {', '.join(ips)}",
                latency_ms=round(latency, 2)
            )
        else:
            loop = asyncio.get_event_loop()
            ip = await loop.run_in_executor(None, socket.gethostbyname, domain)
            latency = (time.monotonic() - start) * 1000
            return CheckResult(
                check_type="DNS",
                status="healthy",
                value=ip,
                message=f"DNS çözümlendi → {ip}",
                latency_ms=round(latency, 2)
            )
    except Exception:
        latency = (time.monotonic() - start) * 1000
        return CheckResult(
            check_type="DNS",
            status="error",
            message="DNS çözümlenemedi — kayıt yok veya sunucu yanıt vermiyor",
            latency_ms=round(latency, 2)
        )


async def check_http(domain: str) -> CheckResult:
    if not domain:
        return CheckResult(check_type="HTTP", status="skipped", message="Domain belirtilmedi")

    url = f"https://{domain}" if not domain.startswith("http") else domain
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(url)
            latency = (time.monotonic() - start) * 1000
            status = "healthy" if response.status_code < 400 else "warning"
            return CheckResult(
                check_type="HTTP",
                status=status,
                value=str(response.status_code),
                message=f"HTTP {response.status_code} — {url}",
                latency_ms=round(latency, 2)
            )
    except httpx.ConnectError:
        try:
            http_url = f"http://{domain}" if not domain.startswith("http") else domain
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                response = await client.get(http_url)
                latency = (time.monotonic() - start) * 1000
                return CheckResult(
                    check_type="HTTP",
                    status="warning",
                    value=str(response.status_code),
                    message=f"HTTPS başarısız, HTTP {response.status_code} — {http_url}",
                    latency_ms=round(latency, 2)
                )
        except Exception:
            latency = (time.monotonic() - start) * 1000
            return CheckResult(
                check_type="HTTP",
                status="error",
                message="HTTP/HTTPS bağlantısı kurulamadı",
                latency_ms=round(latency, 2)
            )
    except Exception:
        latency = (time.monotonic() - start) * 1000
        return CheckResult(
            check_type="HTTP",
            status="error",
            message="HTTP isteği başarısız oldu",
            latency_ms=round(latency, 2)
        )


async def check_ssl(domain: str) -> CheckResult:
    if not domain:
        return CheckResult(check_type="SSL", status="skipped", message="Domain belirtilmedi")

    clean_domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
    start = time.monotonic()
    try:
        context = ssl.create_default_context()
        conn = context.wrap_socket(
            socket.socket(socket.AF_INET),
            server_hostname=clean_domain
        )
        conn.settimeout(10)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: conn.connect((clean_domain, 443)))

        cert = conn.getpeercert()
        conn.close()

        latency = (time.monotonic() - start) * 1000

        not_after = cert.get("notAfter", "")
        subject = dict(x[0] for x in cert.get("subject", []))
        cn = subject.get("commonName", clean_domain)

        return CheckResult(
            check_type="SSL",
            status="healthy",
            value=cn,
            message=f"SSL geçerli — CN: {cn}, Son geçerlilik: {not_after}",
            latency_ms=round(latency, 2)
        )
    except ssl.SSLCertVerificationError:
        latency = (time.monotonic() - start) * 1000
        return CheckResult(
            check_type="SSL",
            status="error",
            message="SSL sertifikası geçersiz veya güvenilir değil",
            latency_ms=round(latency, 2)
        )
    except Exception:
        latency = (time.monotonic() - start) * 1000
        return CheckResult(
            check_type="SSL",
            status="error",
            message="SSL bağlantısı kurulamadı",
            latency_ms=round(latency, 2)
        )


async def check_ping(host: str) -> CheckResult:
    if not host:
        return CheckResult(check_type="PING", status="skipped", message="Host belirtilmedi")

    start = time.monotonic()
    try:
        clean_host = host.replace("https://", "").replace("http://", "").split("/")[0]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((clean_host, 80))
        sock.close()
        latency = (time.monotonic() - start) * 1000

        if result == 0:
            return CheckResult(
                check_type="PING",
                status="healthy",
                value=clean_host,
                message=f"Host erişilebilir — port 80 açık",
                latency_ms=round(latency, 2)
            )
        else:
            sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock2.settimeout(5)
            result2 = sock2.connect_ex((clean_host, 443))
            sock2.close()
            latency = (time.monotonic() - start) * 1000
            if result2 == 0:
                return CheckResult(
                    check_type="PING",
                    status="healthy",
                    value=clean_host,
                    message=f"Host erişilebilir — port 443 açık",
                    latency_ms=round(latency, 2)
                )
            return CheckResult(
                check_type="PING",
                status="error",
                message=f"Host erişilemiyor (port 80/443 kapalı)",
                latency_ms=round(latency, 2)
            )
    except socket.gaierror:
        latency = (time.monotonic() - start) * 1000
        return CheckResult(
            check_type="PING",
            status="error",
            message="DNS çözümlenemiyor — host bulunamadı",
            latency_ms=round(latency, 2)
        )
    except Exception:
        latency = (time.monotonic() - start) * 1000
        return CheckResult(
            check_type="PING",
            status="error",
            message="Host bağlantısı başarısız",
            latency_ms=round(latency, 2)
        )


async def check_whois_expiry(domain: str) -> CheckResult:
    if not domain:
        return CheckResult(check_type="WHOIS", status="skipped", message="Domain belirtilmedi")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            clean = domain.replace("https://", "").replace("http://", "").split("/")[0]
            response = await client.get(f"https://api.whoisjson.com/v1/{clean}")
            if response.status_code == 200:
                data = response.json()
                expires = data.get("expires", "Bilinmiyor")
                return CheckResult(
                    check_type="WHOIS",
                    status="healthy",
                    value=expires,
                    message=f"Domain bitiş tarihi: {expires}"
                )
    except Exception:
        pass

    return CheckResult(
        check_type="WHOIS",
        status="warning",
        message="WHOIS bilgisi alınamadı (harici API)"
    )


def build_summary(results: list[CheckResult]) -> str:
    statuses = [r.status for r in results]
    if all(s == "healthy" for s in statuses if s != "skipped"):
        return "Tüm kontroller başarılı — sistem sağlıklı görünüyor."
    elif "error" in statuses:
        errors = [r.check_type for r in results if r.status == "error"]
        return f"Kritik sorunlar tespit edildi: {', '.join(errors)}"
    elif "warning" in statuses:
        warnings = [r.check_type for r in results if r.status == "warning"]
        return f"Uyarılar mevcut: {', '.join(warnings)}"
    return "Kontroller tamamlandı."


@router.post("/run", response_model=CheckResponse)
@limiter.limit("10/minute")
async def run_checks(request: Request, payload: CheckRequest):
    tasks = []

    # Domain formatını doğrula
    domain = None
    if payload.domain:
        domain = _validate_domain(payload.domain)

    host = domain or payload.server_ip

    if domain:
        tasks.append(check_dns(domain))
        tasks.append(check_http(domain))
        tasks.append(check_ssl(domain))

    if host:
        tasks.append(check_ping(host))  # host = validated domain or user's own server_ip

    if not tasks:
        return CheckResponse(results=[], summary="Kontrol yapılacak domain veya IP belirtilmedi.")

    results = await asyncio.gather(*tasks)
    results = list(results)
    summary = build_summary(results)

    return CheckResponse(results=results, summary=summary)
