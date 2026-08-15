"""Blacklist / RBL kontrolü — IP'nin spam kara listelerindeki durumu.

En büyük doğruluk tuzağı: birçok RBL (Spamhaus, UCEPROTECT, SORBS) açık
resolver'lardan (8.8.8.8 gibi) gelen sorguları REDDEDER ve 127.255.255.x
sentinel kodları döner. Bu tespit edilmezse araç sessizce yalan söyler:
listeli bir IP "temiz" görünür. Bu yüzden:

1. RBL sorguları SİSTEM resolver'ından çıkar — CLAUDE.md'deki "public
   resolver kullan" kuralına AÇIK istisna: o kural panelin DNS teşhisi için
   yerel önbelleği miras almaması içindir; RBL'de ise public resolver
   kullanmak sorgunun reddedilmesine yol açar.
2. `_is_query_refused()` sentinel kodları yakalar → sonuç "temiz" değil
   "sorgu reddedildi" olur.
3. 127.0.0.0/8 dışında dönen yanıt geçersizdir (süresi dolup park edilmiş
   bölgelerin wildcard'ı her IP'yi "listeli" gösterir) → hata sayılır.

Sorgular async resolver + Semaphore(10) ile çıkar: 28 bölge × eşzamanlı IP
sorgusu thread havuzunu doldurmaz, Hızlı Kontrol bloklanmaz.
"""
import asyncio
import ipaddress
import time
from typing import Optional

import dns.asyncresolver
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import dns_core
from error_analysis import get_error_by_key
from net_validation import validate_host
from rate_limiter import limiter
from routers.quick_check import ErrorAnalysis

router = APIRouter(prefix="/api/blacklist", tags=["blacklist"])

QUERY_TIMEOUT = 5.0
MAX_IPS = 5          # domain çok IP'ye çözülürse ilk 5'i kontrol edilir
MAX_CONCURRENCY = 10  # bölge sorguları için eşzamanlılık sınırı (istek başına)
# Not: Semaphore modül seviyesinde OLUŞTURULMAZ — asyncio.Semaphore ilk
# kullanıldığı event loop'a bağlanır ve başka loop'tan kullanımda patlar
# (test/reload senaryoları). İstek başına oluşturulur.

# ── Bölgeler ──────────────────────────────────────────────────────────────────
# code_map: dönen 127.x.y.z kodunun ANLAMI — Spamhaus'ta 127.0.0.10 ("dinamik
# IP politikası") ile 127.0.0.2 (SBL, gerçek spam kaynağı) aynı şey değildir.
# code_map'i olmayan bölgede her geçerli 127.x kodu "listeli" sayılır.
ZONES = [
    {"zone": "zen.spamhaus.org", "name": "Spamhaus ZEN", "code_map": {
        "127.0.0.2":  "SBL — doğrulanmış spam kaynağı",
        "127.0.0.3":  "SBL CSS — snowshoe/düşük itibarlı gönderim",
        "127.0.0.4":  "XBL — virüslü / botnet üyesi (CBL)",
        "127.0.0.9":  "SBL DROP — ele geçirilmiş ağ bloğu",
        "127.0.0.10": "PBL — ISP dinamik IP politikası (spam kanıtı DEĞİL)",
        "127.0.0.11": "PBL — Spamhaus dinamik IP politikası (spam kanıtı DEĞİL)",
    }},
    {"zone": "bl.spamcop.net",           "name": "SpamCop"},
    {"zone": "b.barracudacentral.org",   "name": "Barracuda"},
    {"zone": "dnsbl.sorbs.net",          "name": "SORBS (toplu)", "code_map": {
        "127.0.0.2":  "HTTP proxy",
        "127.0.0.3":  "SOCKS proxy",
        "127.0.0.4":  "Diğer proxy",
        "127.0.0.5":  "Açık SMTP relay",
        "127.0.0.6":  "Spam kaynağı",
        "127.0.0.7":  "Web formu kötüye kullanımı",
        "127.0.0.8":  "Engellenmesi istenen blok",
        "127.0.0.9":  "Zombi / ele geçirilmiş",
        "127.0.0.10": "Dinamik IP aralığı (spam kanıtı DEĞİL)",
        "127.0.0.14": "noserver — mail sunucusu olmamalı",
    }},
    {"zone": "spam.dnsbl.sorbs.net",     "name": "SORBS Spam"},
    {"zone": "psbl.surriel.com",         "name": "PSBL"},
    {"zone": "dnsbl-1.uceprotect.net",   "name": "UCEPROTECT L1"},
    {"zone": "dnsbl-2.uceprotect.net",   "name": "UCEPROTECT L2 (ağ bloğu)"},
    {"zone": "dnsbl-3.uceprotect.net",   "name": "UCEPROTECT L3 (ASN)"},
    {"zone": "all.s5h.net",              "name": "s5h.net"},
    {"zone": "ix.dnsbl.manitu.net",      "name": "Manitu (NiX Spam)"},
    {"zone": "dyna.spamrats.com",        "name": "SpamRats Dyna (dinamik IP)"},
    {"zone": "noptr.spamrats.com",       "name": "SpamRats NoPtr (PTR yok)"},
    {"zone": "spam.spamrats.com",        "name": "SpamRats Spam"},
    {"zone": "bl.0spam.org",             "name": "0Spam"},
    {"zone": "dnsbl.dronebl.org",        "name": "DroneBL"},
    {"zone": "db.wpbl.info",             "name": "WPBL"},
    {"zone": "rbl.interserver.net",      "name": "InterServer"},
    {"zone": "truncate.gbudb.net",       "name": "GBUdb Truncate"},
    # dnsbl.spfbl.net bilinçli olarak listede DEĞİL: temiz IP'lere belgelenmemiş
    # politika kodları (127.0.0.4) dönüyor — yanlış pozitif üretir.
    {"zone": "bl.blocklist.de",          "name": "blocklist.de"},
    {"zone": "ips.backscatterer.org",    "name": "Backscatterer"},
    {"zone": "bl.nordspam.com",          "name": "NordSpam"},
    {"zone": "bip.virusfree.cz",         "name": "Virusfree"},
    {"zone": "rbl.efnetrbl.org",         "name": "EFnet RBL"},
    {"zone": "bl.spameatingmonkey.net",  "name": "SpamEatingMonkey"},
    {"zone": "ubl.unsubscore.com",       "name": "UnsubScore (Lashback)"},
    {"zone": "cbl.abuseat.org",          "name": "CBL (Abuseat)"},
]


def _is_query_refused(codes: list[str]) -> bool:
    """Açık/public resolver reddi sentinel'leri (Spamhaus: 127.255.255.252
    yazım hatası, .254 açık resolver, .255 aşırı hacim)."""
    return any(c.startswith("127.255.255.") for c in codes)


def _make_rbl_resolver() -> dns.asyncresolver.Resolver:
    # AÇIK İSTİSNA (modül docstring'i): RBL sorguları sistem resolver'ından
    # çıkar; public resolver kullanmak reddedilmeye yol açar.
    try:
        r = dns.asyncresolver.Resolver(configure=True)
        if not r.nameservers:
            raise ValueError("sistem resolver'ı bulunamadı")
    except Exception:
        r = dns_core.make_async_resolver()  # son çare: public resolver
    r.timeout = QUERY_TIMEOUT
    r.lifetime = QUERY_TIMEOUT
    return r


# ── Modeller ──────────────────────────────────────────────────────────────────

class BlacklistRequest(BaseModel):
    target: str            # IPv4 veya alan adı


class ZoneResult(BaseModel):
    zone: str
    name: str
    status: str            # healthy (temiz) | error (listeli) | warning (doğrulanamadı) | info
    detail: str
    codes: list[str] = []
    latency_ms: Optional[float] = None


class IPReport(BaseModel):
    ip: str
    listed_count: int
    unverified_count: int
    checked_count: int
    zones: list[ZoneResult]


class BlacklistResponse(BaseModel):
    target: str
    ips: list[IPReport]
    overall: str           # healthy | warning | error
    summary: str
    error_analysis: Optional[ErrorAnalysis] = None


# ── Sorgu mantığı ─────────────────────────────────────────────────────────────

async def _check_zone(resolver, ip: str, zone_def: dict, sem: asyncio.Semaphore) -> ZoneResult:
    reversed_ip = ".".join(reversed(ip.split(".")))
    qname = f"{reversed_ip}.{zone_def['zone']}"
    start = time.monotonic()

    async with sem:
        try:
            answers = await resolver.resolve(qname, "A")
            codes = sorted(str(r) for r in answers)
            status_exc = None
        except Exception as exc:
            codes = []
            status_exc = exc

    latency = round((time.monotonic() - start) * 1000, 1)

    if status_exc is not None:
        code, _msg = dns_core.classify_dns_error(status_exc)
        if code in ("nxdomain", "no_answer"):
            return ZoneResult(zone=zone_def["zone"], name=zone_def["name"],
                              status="healthy", detail="Listede değil",
                              latency_ms=latency)
        return ZoneResult(zone=zone_def["zone"], name=zone_def["name"],
                          status="warning",
                          detail="Doğrulanamadı — bölge yanıt vermedi (zaman aşımı/ağ)",
                          latency_ms=latency)

    if _is_query_refused(codes):
        # Sessizce "temiz" DEME: sorgu reddedildi, sonuç bilinmiyor
        return ZoneResult(zone=zone_def["zone"], name=zone_def["name"],
                          status="warning",
                          detail="Sorgu reddedildi — açık/public resolver'dan gelen sorgulara yanıt verilmiyor",
                          codes=codes, latency_ms=latency)

    invalid = [c for c in codes if not ipaddress.ip_address(c).is_loopback]
    if invalid:
        # 127/8 dışı yanıt: park edilmiş bölge wildcard'ı — listeleme kanıtı değil
        return ZoneResult(zone=zone_def["zone"], name=zone_def["name"],
                          status="warning",
                          detail=f"Geçersiz yanıt ({', '.join(invalid[:3])}) — bölge askıda/park edilmiş olabilir",
                          codes=codes, latency_ms=latency)

    code_map = zone_def.get("code_map", {})
    meanings = [code_map.get(c, f"Listeli (kod {c})") for c in codes]
    return ZoneResult(zone=zone_def["zone"], name=zone_def["name"],
                      status="error", detail=" | ".join(meanings),
                      codes=codes, latency_ms=latency)


async def _resolve_target_ips(cleaned: str) -> list[str]:
    """IP girildiyse kendisi; alan adıysa A kayıtları (public resolver uygun)."""
    try:
        ipaddress.ip_address(cleaned)
        return [cleaned]
    except ValueError:
        pass

    res = await dns_core.resolve_async(cleaned, "A", timeout=QUERY_TIMEOUT)
    if res["status"] != "found" or not res["records"]:
        raise HTTPException(400, f"Alan adı IPv4 adresine çözülemedi: {res['error'] or 'A kaydı yok'}")
    return res["records"][:MAX_IPS]


@router.post("/check", response_model=BlacklistResponse)
@limiter.limit("10/minute")
async def check_blacklist(request: Request, payload: BlacklistRequest):
    cleaned = validate_host(payload.target)

    # RBL v1 yalnızca IPv4 — bölgelerin büyük çoğunluğu IPv6 desteklemez
    try:
        ip_obj = ipaddress.ip_address(cleaned)
        if ip_obj.version == 6:
            raise HTTPException(400, "RBL kontrolü yalnızca IPv4 adreslerini destekler")
    except ValueError:
        pass

    ips = await _resolve_target_ips(cleaned)
    resolver = _make_rbl_resolver()
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    reports: list[IPReport] = []
    for ip in ips:
        zone_results = await asyncio.gather(*(_check_zone(resolver, ip, z, sem) for z in ZONES))
        listed = sum(1 for z in zone_results if z.status == "error")
        unverified = sum(1 for z in zone_results if z.status == "warning")
        # Listeli bölgeler üstte, sonra doğrulanamayanlar
        order = {"error": 0, "warning": 1, "healthy": 2, "info": 3}
        zone_results = sorted(zone_results, key=lambda z: order.get(z.status, 4))
        reports.append(IPReport(
            ip=ip, listed_count=listed, unverified_count=unverified,
            checked_count=len(ZONES), zones=list(zone_results),
        ))

    total_listed = sum(r.listed_count for r in reports)
    total_unverified = sum(r.unverified_count for r in reports)

    error_analysis = None
    if total_listed:
        overall = "error"
        ip_word = ", ".join(f"{r.ip} ({r.listed_count} liste)" for r in reports if r.listed_count)
        summary = f"Kara liste kaydı bulundu: {ip_word}. Kod açıklamalarına bakın — her kod aynı ciddiyette değildir."
        entry = get_error_by_key("blacklist")
        if entry:
            error_analysis = ErrorAnalysis(**entry)
    elif total_unverified:
        overall = "warning"
        summary = (
            f"Listeleme bulunamadı; ancak {total_unverified} bölge doğrulanamadı "
            "(sorgu reddedildi veya yanıt yok) — bu bölgeler için sonuç bilinmiyor."
        )
    else:
        overall = "healthy"
        summary = f"Temiz — kontrol edilen {len(ZONES)} bölgenin hiçbirinde kayıt yok."

    return BlacklistResponse(
        target=cleaned, ips=reports, overall=overall,
        summary=summary, error_analysis=error_analysis,
    )
