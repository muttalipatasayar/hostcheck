"""DNS yayılma kontrolü — bir kaydın dünyadaki resolver'larda görünürlüğü.

Asıl değer TR resolver'ları (Türk Telekom, Superonline): destek çağrılarının
çoğu "müşterinin evinden site açılmıyor" şeklindedir ve global resolver'lar
yayılmış görünürken TR ISP önbelleği eski kaydı tutuyor olabilir.

Sorgular async resolver ile çıkar (dns_core.resolve_async) — 13 eşzamanlı
sorgu thread havuzunu doldurmaz, Hızlı Kontrol/DNS Toolbox bloklanmaz.
"""
import asyncio
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from dns_core import resolve_async
from error_analysis import get_error_by_key
from rate_limiter import limiter
from routers.quick_check import ErrorAnalysis, validate_domain

router = APIRouter(prefix="/api/dns-propagation", tags=["dns-propagation"])

QUERY_TIMEOUT = 5.0    # resolver başına; 13 sorgu paralel gittiğinden toplam <12s
MAX_CONCURRENCY = 10   # nazik davran: aynı anda en fazla 10 sorgu (istek başına)
# Not: Semaphore modül seviyesinde OLUŞTURULMAZ — ilk kullanıldığı event
# loop'a bağlanır ve başka loop'tan kullanımda patlar. İstek başına oluşturulur.

# 13 resolver — TR olanlar işin asıl değeri
RESOLVERS = [
    {"name": "Türk Telekom",  "ip": "195.175.39.39",  "location": "Türkiye"},
    {"name": "Superonline",   "ip": "195.114.66.100", "location": "Türkiye"},
    {"name": "Google",        "ip": "8.8.8.8",        "location": "Global"},
    {"name": "Cloudflare",    "ip": "1.1.1.1",        "location": "Global"},
    {"name": "Quad9",         "ip": "9.9.9.9",        "location": "İsviçre"},
    {"name": "OpenDNS",       "ip": "208.67.222.222", "location": "ABD"},
    {"name": "AdGuard",       "ip": "94.140.14.14",   "location": "Kıbrıs"},
    {"name": "CleanBrowsing", "ip": "185.228.168.9",  "location": "ABD"},
    {"name": "Level3",        "ip": "4.2.2.1",        "location": "ABD"},
    {"name": "Neustar",       "ip": "64.6.64.6",      "location": "ABD"},
    {"name": "Comodo",        "ip": "8.26.56.26",     "location": "ABD"},
    {"name": "DNS.WATCH",     "ip": "84.200.69.80",   "location": "Almanya"},
    {"name": "Yandex",        "ip": "77.88.8.8",      "location": "Rusya"},
]

SUPPORTED_TYPES = {"A", "AAAA", "CNAME", "MX", "NS", "TXT"}


class PropagationRequest(BaseModel):
    domain: str
    record_type: str = "A"


class ResolverResult(BaseModel):
    name: str
    ip: str
    location: str
    status: str                     # healthy | warning | error | info
    records: list[str] = []
    ttl: Optional[int] = None
    latency_ms: Optional[float] = None
    detail: Optional[str] = None


class PropagationResponse(BaseModel):
    domain: str
    record_type: str
    results: list[ResolverResult]
    consensus: list[str]            # çoğunluğun gördüğü kayıt kümesi
    propagated_pct: int             # konsensüsü gören resolver yüzdesi
    overall: str                    # healthy | warning | error | info
    summary: str
    error_analysis: Optional[ErrorAnalysis] = None


async def _query_one(resolver: dict, domain: str, rtype: str, sem: asyncio.Semaphore) -> dict:
    start = time.monotonic()
    res = await resolve_async(
        domain, rtype,
        nameservers=[resolver["ip"]], timeout=QUERY_TIMEOUT, semaphore=sem,
    )
    res["latency_ms"] = round((time.monotonic() - start) * 1000, 1)
    res["resolver"] = resolver
    return res


@router.post("/check", response_model=PropagationResponse)
@limiter.limit("15/minute")
async def check_propagation(request: Request, payload: PropagationRequest):
    domain = validate_domain(payload.domain)
    rtype = payload.record_type.strip().upper()
    if rtype not in SUPPORTED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Desteklenmeyen kayıt tipi: {rtype} (desteklenen: {', '.join(sorted(SUPPORTED_TYPES))})",
        )

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    raw = await asyncio.gather(*(_query_one(r, domain, rtype, sem) for r in RESOLVERS))

    # ── Konsensüs: kayıt bulan resolver'ların en sık gördüğü küme ────────────
    found = [r for r in raw if r["status"] == "found"]
    nxdomain = [r for r in raw if r["status"] == "nxdomain"]
    counts: dict[tuple, int] = {}
    for r in found:
        counts[tuple(r["records"])] = counts.get(tuple(r["records"]), 0) + 1
    consensus: list[str] = list(max(counts, key=counts.get)) if counts else []

    results: list[ResolverResult] = []
    agree = 0
    for r in raw:
        info = r["resolver"]
        if r["status"] == "found":
            matches = r["records"] == consensus
            agree += matches
            status = "healthy" if matches else "warning"
            detail = None if matches else "Konsensüsten farklı yanıt — eski önbellek veya yayılma sürüyor olabilir"
        elif r["status"] in ("nxdomain", "no_answer"):
            # Kayıt yokluğu resolver arızası değildir → info
            status = "info"
            detail = r["error"]
        else:
            status = "error"
            detail = r["error"]
        results.append(ResolverResult(
            name=info["name"], ip=info["ip"], location=info["location"],
            status=status, records=r["records"], ttl=r["ttl"],
            latency_ms=r["latency_ms"], detail=detail,
        ))

    propagated_pct = round(100 * agree / len(RESOLVERS))

    # ── Genel durum + Türkçe özet ────────────────────────────────────────────
    # "Her yerde NXDOMAIN" kuralı yanıt VEREN resolver'lar üzerinden işler:
    # panelin ağından bazı resolver'lara hiç ulaşılamayabilir (ör. TR ISP
    # resolver'ları yalnızca kendi abonelerine yanıt verir) — bu, alan adının
    # varlığı hakkında bilgi taşımaz.
    error_analysis = None
    unreachable = [r for r in raw if r["status"] in ("timeout", "no_nameservers", "error")]
    if not found and nxdomain:
        # Yanıt veren herkes NXDOMAIN dedi: tutarlı "kayıt yok" — hata DEĞİL
        overall = "info"
        summary = (
            f"{domain} için {rtype} kaydı, yanıt veren {len(nxdomain)} resolver'ın tümünde bulunamadı (NXDOMAIN). "
            "Alan adı kayıtlı değil veya DNS bölgesi yayında değil."
        )
        if unreachable:
            summary += f" ({len(unreachable)} resolver'a bu ağdan ulaşılamadı.)"
        entry = get_error_by_key("dns_ns")
        if entry:
            error_analysis = ErrorAnalysis(**entry)
    elif not found:
        overall = "error"
        summary = f"Hiçbir resolver {rtype} kaydına ulaşamadı — ad sunucuları yanıt vermiyor olabilir."
        entry = get_error_by_key("dns_ns")
        if entry:
            error_analysis = ErrorAnalysis(**entry)
    elif agree == len(RESOLVERS):
        overall = "healthy"
        summary = f"{rtype} kaydı tüm resolver'larda tutarlı — yayılma tamamlanmış (%100)."
    else:
        overall = "warning"
        summary = (
            f"Resolver'ların %{propagated_pct}'i konsensüs kaydını görüyor — "
            "yayılma sürüyor veya bazı önbellekler eski kaydı tutuyor."
        )
        if rtype == "A":
            entry = get_error_by_key("dns_a")
            if entry:
                error_analysis = ErrorAnalysis(**entry)

    return PropagationResponse(
        domain=domain, record_type=rtype, results=results,
        consensus=consensus, propagated_pct=propagated_pct,
        overall=overall, summary=summary, error_analysis=error_analysis,
    )
