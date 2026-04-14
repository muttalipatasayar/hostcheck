import ipaddress
import re
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from rate_limiter import limiter

router = APIRouter(prefix="/api/ip", tags=["ip-lookup"])

# ip-api.com — ücretsiz, API anahtarı gerektirmez, dakikada 45 istek
_IP_API_URL = "http://ip-api.com/json/{query}?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as,asname,mobile,proxy,hosting,query"

_DOMAIN_RE = re.compile(r'^([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$')
_IPV4_RE   = re.compile(r'^\d{1,3}(\.\d{1,3}){3}$')
_IPV6_RE   = re.compile(r'^[0-9a-fA-F:]+$')


class IPLookupResponse(BaseModel):
    query: str                         # Sorgulanan IP
    country: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    timezone: Optional[str] = None
    isp: Optional[str] = None
    org: Optional[str] = None
    asn: Optional[str] = None          # "AS15169"
    asn_name: Optional[str] = None     # "GOOGLE"
    lat: Optional[float] = None
    lon: Optional[float] = None
    is_mobile: bool = False
    is_proxy: bool = False
    is_hosting: bool = False


def _validate_and_clean(raw: str) -> str:
    """Girdiyi doğrula, temizlenmiş string döndür."""
    q = raw.strip().lower()
    q = re.sub(r'^https?://', '', q)
    q = q.split('/')[0].split('?')[0]

    if not q:
        raise HTTPException(400, "IP adresi veya alan adı zorunludur")

    # IPv4 kontrolü
    if _IPV4_RE.match(q):
        try:
            ip = ipaddress.IPv4Address(q)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise HTTPException(400, "Özel / yerel IP adresleri sorgulanamaz")
            return q
        except ipaddress.AddressValueError:
            raise HTTPException(400, "Geçersiz IPv4 adresi")

    # IPv6 kontrolü
    if ':' in q:
        try:
            ip6 = ipaddress.IPv6Address(q)
            if ip6.is_private or ip6.is_loopback or ip6.is_link_local:
                raise HTTPException(400, "Özel / yerel IPv6 adresleri sorgulanamaz")
            return q
        except ipaddress.AddressValueError:
            raise HTTPException(400, "Geçersiz IPv6 adresi")

    # Domain adı kontrolü
    if _DOMAIN_RE.match(q):
        return q

    raise HTTPException(400, "Geçersiz IP adresi veya alan adı formatı")


@router.get("/lookup", response_model=IPLookupResponse)
@limiter.limit("30/minute")
async def lookup_ip(request: Request, q: str):
    """IP veya alan adı sorgular; ülke, firma, ASN bilgisini döner."""
    query = _validate_and_clean(q)

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(_IP_API_URL.format(query=query))
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(504, "IP sorgulama servisi zaman aşımına uğradı")
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"IP servis hatası: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(502, f"IP sorgulama başarısız: {str(e)[:80]}")

    if data.get("status") == "fail":
        msg = data.get("message", "Bilinmeyen hata")
        if msg == "private range":
            raise HTTPException(400, "Bu IP adresi özel ağ aralığında")
        if msg == "reserved range":
            raise HTTPException(400, "Bu IP adresi rezerve edilmiş bir aralıkta")
        raise HTTPException(400, f"IP sorgulanamadı: {msg}")

    # ASN ayrıştır: "AS15169 Google LLC" → asn="AS15169", asn_name="Google LLC"
    raw_as   = data.get("as", "") or ""
    asn      = raw_as.split(" ")[0] if raw_as else None
    asn_name = data.get("asname") or (raw_as.split(" ", 1)[1] if " " in raw_as else None)

    return IPLookupResponse(
        query=data.get("query", query),
        country=data.get("country"),
        country_code=data.get("countryCode"),
        region=data.get("regionName"),
        city=data.get("city"),
        zip_code=data.get("zip") or None,
        timezone=data.get("timezone"),
        isp=data.get("isp"),
        org=data.get("org"),
        asn=asn or None,
        asn_name=asn_name or None,
        lat=data.get("lat"),
        lon=data.get("lon"),
        is_mobile=bool(data.get("mobile")),
        is_proxy=bool(data.get("proxy")),
        is_hosting=bool(data.get("hosting")),
    )
