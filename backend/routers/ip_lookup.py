import ipaddress
import re
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from net_validation import validate_host
from rate_limiter import limiter

router = APIRouter(prefix="/api/ip", tags=["ip-lookup"])

# ip-api.com — ücretsiz, API anahtarı gerektirmez, dakikada 45 istek
_IP_API_URL = "http://ip-api.com/json/{query}?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as,asname,mobile,proxy,hosting,query"


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
    """Girdiyi doğrula, temizlenmiş string döndür (net_validation'a delege)."""
    return validate_host(raw, allow_ip=True, allow_private=False)


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
