import asyncio
import ipaddress
import socket
import ssl
import time
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from error_analysis import analyze_error, get_error_by_key
from rate_limiter import limiter

try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False

import dns_core

# Hızlı public DNS resolver — sistem DNS'ini bypass et
PUBLIC_DNS = ['8.8.8.8', '1.1.1.1']
DNS_TIMEOUT = 3.0  # saniye


def make_resolver() -> 'dns.resolver.Resolver':
    return dns_core.make_resolver(PUBLIC_DNS, DNS_TIMEOUT)

router = APIRouter(prefix="/api/quick-check", tags=["quick-check"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class QuickCheckRequest(BaseModel):
    domain: str


class CheckItem(BaseModel):
    label: str
    status: str        # healthy | warning | error | info
    value: Optional[str] = None
    detail: Optional[str] = None
    latency_ms: Optional[float] = None
    domain_statuses: list[str] = []   # EPP status kodları (sadece WHOIS satırında dolu)


class ErrorAnalysis(BaseModel):
    title: str
    platform: str
    causes: list[str]
    tech_steps: list[str]
    customer_action: bool
    draft: str


class QuickCheckResponse(BaseModel):
    domain: str
    checks: list[CheckItem]
    overall: str           # healthy | warning | error
    summary: str
    error_analysis: Optional[ErrorAnalysis] = None
    http_status: Optional[int] = None


# ── Domain validation ─────────────────────────────────────────────────────────

# RFC 1035 uyumlu domain formatı (küçük harf, sayı, tire)
_DOMAIN_RE = re.compile(r'^([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$')
_MAX_DOMAIN_LEN = 253
_BLOCKED_KEYWORDS = {'localhost', '::1', '0.0.0.0'}


def clean_domain(domain: str) -> str:
    domain = domain.strip().lower()
    # Null byte temizle
    domain = domain.replace('\x00', '')
    domain = re.sub(r'^https?://', '', domain)
    domain = domain.split('/')[0].split('?')[0].split('#')[0]
    return domain


def validate_domain(raw: str) -> str:
    """SSRF + format koruması. Geçersizse HTTPException(400) fırlatır."""
    if not raw or '\x00' in raw:
        raise HTTPException(status_code=400, detail="Geçersiz domain")

    domain = clean_domain(raw)

    if not domain:
        raise HTTPException(status_code=400, detail="Domain boş olamaz")

    if len(domain) > _MAX_DOMAIN_LEN:
        raise HTTPException(status_code=400, detail=f"Domain en fazla {_MAX_DOMAIN_LEN} karakter olabilir")

    if domain in _BLOCKED_KEYWORDS:
        raise HTTPException(status_code=400, detail="Bu domain sorgulanamaz")

    # IP adresi mi? (hem IPv4 hem IPv6)
    try:
        ip = ipaddress.ip_address(domain)
        # Private, loopback, link-local, reserved, multicast → reddet
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise HTTPException(status_code=400, detail="Özel/dahili IP adresleri sorgulanamaz")
        raise HTTPException(status_code=400, detail="IP adresi yerine domain adı girin")
    except ValueError:
        pass  # IP değil — domain formatı kontrolüne geç

    if not _DOMAIN_RE.match(domain):
        raise HTTPException(status_code=400, detail="Geçersiz domain formatı (örnek: example.com)")

    return domain


# ── Individual checks ─────────────────────────────────────────────────────────

def _is_tr_domain(domain: str) -> bool:
    """Alan adı .tr uzantılı mı?"""
    tr_tlds = ('.com.tr', '.net.tr', '.org.tr', '.av.tr', '.biz.tr',
               '.info.tr', '.tv.tr', '.tel.tr', '.name.tr', '.gov.tr',
               '.edu.tr', '.mil.tr', '.k12.tr', '.pol.tr', '.web.tr', '.tr')
    return any(domain.endswith(t) for t in tr_tlds)


def _raw_whois(server: str, query: str, timeout: float = 8.0) -> str:
    """Port 43 üzerinden ham WHOIS sorgusu yap"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect((server, 43))
        s.sendall((query + "\r\n").encode())
        chunks = []
        while True:
            data = s.recv(4096)
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks).decode(errors='ignore')


def _get_whois_server_from_iana(tld: str, timeout: float = 5.0) -> str | None:
    """IANA'dan TLD için yetkili WHOIS sunucusunu bul"""
    try:
        resp = _raw_whois("whois.iana.org", tld, timeout)
        for line in resp.splitlines():
            if line.lower().startswith("whois:"):
                server = line.split(":", 1)[1].strip()
                return server if server else None
    except Exception:
        pass
    return None


# Yaygın TLD → WHOIS sunucu haritası (IANA'ya gitmeden hızlı çözüm)
WHOIS_SERVERS = {
    'com': 'whois.verisign-grs.com',
    'net': 'whois.verisign-grs.com',
    'org': 'whois.pir.org',
    'io':  'whois.nic.io',
    'co':  'whois.nic.co',
    'info':'whois.afilias.net',
    'biz': 'whois.biz',
    'online': 'whois.nic.online',
    'site': 'whois.nic.site',
    'store': 'whois.nic.store',
    'app':  'whois.nic.google',
    'dev':  'whois.nic.google',
    'xyz':  'whois.nic.xyz',
    'club': 'whois.nic.club',
    'shop': 'whois.nic.shop',
    'tech': 'whois.nic.tech',
    'eu':   'whois.eu',
    'de':   'whois.denic.de',
    'fr':   'whois.nic.fr',
    'nl':   'whois.domain-registry.nl',
    'uk':   'whois.nic.uk',
    'com.tr': 'whois.trabis.gov.tr',
    'net.tr': 'whois.trabis.gov.tr',
    'org.tr': 'whois.trabis.gov.tr',
    'gov.tr': 'whois.trabis.gov.tr',
    'edu.tr': 'whois.trabis.gov.tr',
    'av.tr':  'whois.trabis.gov.tr',
    'biz.tr': 'whois.trabis.gov.tr',
    'tr':     'whois.trabis.gov.tr',
}

# Tarih formatları (WHOIS yanıtlarında farklı formatlar var)
EXPIRY_PATTERNS = [
    # Trabis formatı: "Expires on..............: 2027-Jan-13."
    (re.compile(r'Expires on[.\s]*:\s*(\d{4}-\w{3}-\d{2})\.?', re.I), '%Y-%b-%d'),
    # Standart ISO
    (re.compile(r'(?:Registry Expiry Date|Expiry Date|Expiration Date|paid-till|renewal-date|Valid Until):\s*(\d{4}-\d{2}-\d{2})', re.I), '%Y-%m-%d'),
    # ISO datetime
    (re.compile(r'(?:Registry Expiry Date|Expiry Date|Expiration Date):\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', re.I), '%Y-%m-%dT%H:%M:%S'),
    # DD-Mon-YYYY
    (re.compile(r'(?:Expiration Date|expires):\s*(\d{2}-\w{3}-\d{4})', re.I), '%d-%b-%Y'),
    # DD/MM/YYYY
    (re.compile(r'(?:Expiration Date|Expiry):\s*(\d{2}/\d{2}/\d{4})', re.I), '%d/%m/%Y'),
    # DD.MM.YYYY
    (re.compile(r'(?:Expiration Date|Expiry):\s*(\d{2}\.\d{2}\.\d{4})', re.I), '%d.%m.%Y'),
]

REGISTRAR_PATTERNS = [
    re.compile(r'Sponsoring Registrar:\s*(.+)', re.I),
    re.compile(r'registrar-name:\s*(.+)', re.I),
    # Trabis formatı: "Organization Name	: Çizgi Telekomünikasyon A.Ş."
    re.compile(r'Organization Name\s*:\s*(.+)', re.I),
    re.compile(r'Registrar:\s*(.+\S)', re.I),
]


def _parse_whois_statuses(raw: str) -> list[str]:
    """WHOIS metninden EPP domain status kodlarını çıkar.

    Desteklenen formatlar:
      - Standart: "Domain Status: clientTransferProhibited https://..."
      - Trabis:   "Status              : Active"
    """
    statuses: list[str] = []

    # Standart ICANN WHOIS: "Domain Status: clientTransferProhibited"
    for m in re.finditer(r'^Domain\s+Status\s*:\s*([a-zA-Z]+)', raw, re.I | re.M):
        s = m.group(1).strip()
        if s and s not in statuses:
            statuses.append(s)

    # Trabis / DENIC gibi sitelerde sadece "Status: Active"
    if not statuses:
        for m in re.finditer(r'^Status\s*:\s*([a-zA-Z]+)', raw, re.I | re.M):
            s = m.group(1).strip()
            if s and s not in statuses:
                statuses.append(s)

    return statuses


# EPP status kodlarının Türkçe karşılıkları ve önem derecesi
# (detail metnine eklenir, frontend de ayrıca badge olarak gösterir)
_EPP_LABELS: dict[str, str] = {
    'ok':                       'Aktif',
    'active':                   'Aktif',
    'clienttransferprohibited': 'Transfer Kilitli',
    'servertransferprohibited': 'Transfer Kilitli (Kayıt Kuruluşu)',
    'clienthold':               'Askıda — DNS yayını yok!',
    'serverhold':               'Askıda — Sunucu Engeli',
    'pendingtransfer':          'Transfer Bekliyor',
    'pendingdelete':            'Silinme Bekliyor',
    'redemptionperiod':         'Kurtarma Sürecinde',
    'clientdeleteprohibited':   'Silme Kilitli',
    'serverdeleteprohibited':   'Silme Kilitli (Kayıt Kuruluşu)',
    'clientupdateprohibited':   'Güncelleme Kilitli',
    'clientrenewprohibited':    'Yenileme Kilitli',
    'addperiod':                'Yeni Kayıt (Koruma Süresi)',
}

# Bu statüsler varsa WHOIS satırını "error" yap
_CRITICAL_STATUSES = {'clienthold', 'serverhold', 'pendingdelete', 'redemptionperiod'}


def _parse_whois_expiry(raw: str) -> tuple[datetime | None, str]:
    """WHOIS metninden son geçerlilik tarihi ve kayıt kuruluşunu çıkar"""
    exp_date = None
    for pattern, fmt in EXPIRY_PATTERNS:
        m = pattern.search(raw)
        if m:
            date_str = m.group(1).strip()[:19]
            try:
                exp_date = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue

    registrar = ""
    for pattern in REGISTRAR_PATTERNS:
        m = pattern.search(raw)
        if m:
            registrar = m.group(1).strip()[:60]
            break

    return exp_date, registrar


def _whois_result_to_check(
    exp_date: datetime | None,
    registrar: str,
    domain: str,
    statuses: list[str] | None = None,
) -> CheckItem:
    """Tarih + EPP status bilgisinden CheckItem oluştur"""
    now = datetime.now(timezone.utc)
    statuses = statuses or []
    statuses_lower = [s.lower() for s in statuses]

    # Kritik EPP durumu var mı?
    has_critical = any(s in _CRITICAL_STATUSES for s in statuses_lower)

    # Status satırına Türkçe karşılıkları ekle (detail için)
    status_notes = [
        _EPP_LABELS.get(s, s)
        for s in statuses_lower
        if s not in ('ok', 'active')   # bunlar zaten "normal" — gürültü yaratmayalım
    ]

    if exp_date is None:
        status_suffix = (f" | {', '.join(status_notes)}" if status_notes else "")
        return CheckItem(
            label="WHOIS / Alan Adı",
            status="error" if has_critical else "info",
            value="Tarih alınamadı",
            detail=f"WHOIS yanıtı alındı ancak bitiş tarihi ayrıştırılamadı"
                   f"{(' | Kayıt: ' + registrar) if registrar else ''}{status_suffix}",
            domain_statuses=statuses,
        )

    days_left = (exp_date - now).days
    exp_str = exp_date.strftime('%d.%m.%Y')
    reg_str = f" | Kayıt: {registrar}" if registrar else ""
    status_str = f" | {', '.join(status_notes)}" if status_notes else ""

    if has_critical:
        item_status = "error"
        note = f" | ⚠ {', '.join(status_notes)}" if status_notes else ""
        value = "Askıda / Kilitli"
        detail = f"Bitiş: {exp_str} — Domain aktif değil!{reg_str}{note}"
    elif days_left < 0:
        item_status = "error"
        value = "Süresi dolmuş"
        detail = f"Alan adı {abs(days_left)} gün önce sona erdi! ({exp_str}){reg_str}{status_str}"
    elif days_left < 15:
        item_status = "error"
        value = f"{days_left} gün kaldı"
        detail = f"Bitiş: {exp_str} — ACİL yenilenmeli!{reg_str}{status_str}"
    elif days_left < 30:
        item_status = "warning"
        value = f"{days_left} gün kaldı"
        detail = f"Bitiş: {exp_str} — Yakında yenilenecek{reg_str}{status_str}"
    else:
        item_status = "healthy"
        value = f"{days_left} gün kaldı"
        detail = f"Bitiş: {exp_str}{reg_str}{status_str}"

    return CheckItem(
        label="WHOIS / Alan Adı",
        status=item_status,
        value=value,
        detail=detail,
        domain_statuses=statuses,
    )


async def do_whois(domain: str) -> CheckItem:
    """WHOIS — port 43 protokolü ile direkt sorgulama"""
    loop = asyncio.get_event_loop()

    def _query_whois() -> CheckItem:
        # WHOIS sunucusunu belirle
        if _is_tr_domain(domain):
            server = 'whois.trabis.gov.tr'
        else:
            # Uzantıya göre bilinen sunucu listesinden bak
            parts = domain.split('.')
            # Önce çift uzantı (com.tr gibi)
            if len(parts) >= 3:
                double_ext = '.'.join(parts[-2:])
                server = WHOIS_SERVERS.get(double_ext)
            else:
                server = None

            if not server:
                tld = parts[-1]
                server = WHOIS_SERVERS.get(tld)

            if not server:
                # IANA'dan bul
                tld = parts[-1]
                server = _get_whois_server_from_iana(tld, timeout=4.0)

            if not server:
                return CheckItem(
                    label="WHOIS / Alan Adı",
                    status="warning",
                    value="Sunucu bulunamadı",
                    detail=f"Bu TLD için WHOIS sunucusu tespit edilemedi"
                )

        try:
            raw = _raw_whois(server, domain, timeout=8.0)
        except Exception as e:
            return CheckItem(
                label="WHOIS / Alan Adı",
                status="warning",
                value="Bağlantı hatası",
                detail=f"WHOIS sunucusuna ({server}) bağlanılamadı: {str(e)[:60]}"
            )

        if not raw or len(raw) < 30:
            return CheckItem(
                label="WHOIS / Alan Adı",
                status="warning",
                value="Yanıt alınamadı",
                detail=f"WHOIS sunucusu ({server}) boş yanıt döndü"
            )

        # "No match" / "NOT FOUND" kontrolü
        lower = raw.lower()
        if any(x in lower for x in ['no match', 'not found', 'no entries', 'no data found', 'object does not exist']):
            return CheckItem(
                label="WHOIS / Alan Adı",
                status="error",
                value="Kayıtlı değil",
                detail=f"Alan adı WHOIS'te bulunamadı — süresi dolmuş veya hiç kayıt edilmemiş olabilir"
            )

        exp_date, registrar = _parse_whois_expiry(raw)
        statuses = _parse_whois_statuses(raw)
        return _whois_result_to_check(exp_date, registrar, domain, statuses)

    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _query_whois),
            timeout=12.0
        )
    except asyncio.TimeoutError:
        return CheckItem(
            label="WHOIS / Alan Adı",
            status="warning",
            value="Zaman aşımı",
            detail="WHOIS sorgusu 12 saniyede tamamlanamadı"
        )
    except Exception as e:
        return CheckItem(
            label="WHOIS / Alan Adı",
            status="warning",
            value="Hata",
            detail=f"WHOIS sorgusu başarısız: {str(e)[:80]}"
        )


async def do_dns_ns(domain: str) -> CheckItem:
    """NS kaydı kontrolü"""
    start = time.monotonic()
    try:
        if DNS_AVAILABLE:
            resolver = make_resolver()
            loop = asyncio.get_event_loop()
            answers = await loop.run_in_executor(None, lambda: resolver.resolve(domain, 'NS'))
            ns_list = [str(r).rstrip('.') for r in answers]
            latency = (time.monotonic() - start) * 1000
            return CheckItem(
                label="DNS / NS Kayıtları",
                status="healthy",
                value=", ".join(ns_list[:3]),
                detail=f"{len(ns_list)} NS kaydı bulundu",
                latency_ms=round(latency, 1)
            )
        else:
            raise Exception("dnspython yok")
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        err_short = str(e).split(':')[0][:60]
        return CheckItem(
            label="DNS / NS Kayıtları",
            status="error",
            value="NS yanıt vermiyor",
            detail=f"NS sorgusu başarısız: {err_short}",
            latency_ms=round(latency, 1)
        )


async def do_dns_a(domain: str) -> CheckItem:
    """A kaydı kontrolü"""
    start = time.monotonic()
    try:
        if DNS_AVAILABLE:
            resolver = make_resolver()
            loop = asyncio.get_event_loop()
            answers = await loop.run_in_executor(None, lambda: resolver.resolve(domain, 'A'))
            ips = [str(r) for r in answers]
            latency = (time.monotonic() - start) * 1000
            return CheckItem(
                label="DNS / A Kaydı",
                status="healthy",
                value=", ".join(ips),
                detail=f"Alan adı {', '.join(ips)} adresine yönleniyor",
                latency_ms=round(latency, 1)
            )
        else:
            loop = asyncio.get_event_loop()
            ip = await loop.run_in_executor(None, socket.gethostbyname, domain)
            latency = (time.monotonic() - start) * 1000
            return CheckItem(
                label="DNS / A Kaydı",
                status="healthy",
                value=ip,
                detail=f"Alan adı {ip} adresine yönleniyor",
                latency_ms=round(latency, 1)
            )
    except Exception:
        latency = (time.monotonic() - start) * 1000
        return CheckItem(
            label="DNS / A Kaydı",
            status="error",
            value="Çözümlenemiyor",
            detail="A kaydı bulunamadı veya DNS yanıt vermiyor",
            latency_ms=round(latency, 1)
        )


async def do_dns_mx(domain: str) -> CheckItem:
    """MX kaydı kontrolü"""
    try:
        if DNS_AVAILABLE:
            resolver = make_resolver()
            loop = asyncio.get_event_loop()
            answers = await loop.run_in_executor(None, lambda: resolver.resolve(domain, 'MX'))
            mx_list = [(r.preference, str(r.exchange).rstrip('.')) for r in answers]
            mx_list.sort()
            mx_str = ", ".join([f"{pref} {exc}" for pref, exc in mx_list[:3]])
            return CheckItem(
                label="DNS / MX Kaydı",
                status="healthy",
                value=mx_str,
                detail=f"{len(mx_list)} MX kaydı bulundu"
            )
    except dns.resolver.NXDOMAIN:
        return CheckItem(label="DNS / MX Kaydı", status="error", value="Kayıt yok", detail="MX kaydı tanımlanmamış — mail hizmeti çalışmayabilir")
    except Exception:
        pass

    return CheckItem(
        label="DNS / MX Kaydı",
        status="warning",
        value="Sorgulanamadı",
        detail="MX kaydı alınamadı"
    )


async def do_ssl(domain: str) -> CheckItem:
    """SSL sertifika kontrolü"""
    start = time.monotonic()
    try:
        context = ssl.create_default_context()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        conn = context.wrap_socket(sock, server_hostname=domain)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: conn.connect((domain, 443)))
        cert = conn.getpeercert()
        conn.close()
        latency = (time.monotonic() - start) * 1000

        not_after_str = cert.get("notAfter", "")
        if not_after_str:
            exp = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            days_left = (exp - datetime.now(timezone.utc)).days
            exp_formatted = exp.strftime("%d.%m.%Y")

            if days_left < 0:
                status, detail = "error", f"Sertifika süresi dolmuş! ({exp_formatted})"
            elif days_left < 15:
                status, detail = "error", f"Sertifika {days_left} gün içinde bitiyor — ACİL yenilenecek ({exp_formatted})"
            elif days_left < 30:
                status, detail = "warning", f"Sertifika {days_left} gün içinde bitiyor ({exp_formatted})"
            else:
                status, detail = "healthy", f"Geçerli | {days_left} gün kaldı | Bitiş: {exp_formatted}"

            return CheckItem(
                label="SSL Sertifika",
                status=status,
                value=f"{days_left} gün" if days_left > 0 else "Süresi dolmuş",
                detail=detail,
                latency_ms=round(latency, 1)
            )
    except ssl.SSLCertVerificationError as e:
        latency = (time.monotonic() - start) * 1000
        return CheckItem(
            label="SSL Sertifika",
            status="error",
            value="Geçersiz sertifika",
            detail=f"SSL doğrulama hatası: {str(e)[:100]}",
            latency_ms=round(latency, 1)
        )
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return CheckItem(
            label="SSL Sertifika",
            status="warning",
            value="HTTPS yok",
            detail=f"SSL bağlantısı kurulamadı — sitenin HTTPS'i olmayabilir",
            latency_ms=round(latency, 1)
        )


async def do_http(domain: str) -> tuple[CheckItem, int | None]:
    """HTTP durum kodu kontrolü — kodu da döndür (analiz için)"""
    url = f"https://{domain}"
    start = time.monotonic()
    status_code = None

    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            r = await client.get(url)
            status_code = r.status_code
            latency = (time.monotonic() - start) * 1000

            if status_code < 400:
                item = CheckItem(
                    label="HTTP Erişim",
                    status="healthy",
                    value=f"{status_code} OK",
                    detail=f"Site erişilebilir | Son URL: {str(r.url)[:60]}",
                    latency_ms=round(latency, 1)
                )
            elif status_code == 403:
                item = CheckItem(
                    label="HTTP Erişim",
                    status="warning",
                    value=f"{status_code} Forbidden",
                    detail="Erişim engellendi — izin veya konfigürasyon sorunu",
                    latency_ms=round(latency, 1)
                )
            elif status_code == 404:
                item = CheckItem(
                    label="HTTP Erişim",
                    status="warning",
                    value=f"{status_code} Not Found",
                    detail="Sayfa bulunamadı — dosya yok veya .htaccess sorunu",
                    latency_ms=round(latency, 1)
                )
            elif status_code >= 500:
                item = CheckItem(
                    label="HTTP Erişim",
                    status="error",
                    value=f"{status_code} Server Error",
                    detail="Sunucu hatası — uygulama çalışmıyor olabilir",
                    latency_ms=round(latency, 1)
                )
            else:
                item = CheckItem(
                    label="HTTP Erişim",
                    status="warning",
                    value=str(status_code),
                    detail=f"HTTP {status_code} yanıtı alındı",
                    latency_ms=round(latency, 1)
                )
            return item, status_code

    except httpx.ConnectError:
        # HTTPS bağlanamadı, HTTP dene
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                r = await client.get(f"http://{domain}")
                status_code = r.status_code
                latency = (time.monotonic() - start) * 1000
                return CheckItem(
                    label="HTTP Erişim",
                    status="warning",
                    value=f"HTTP {status_code}",
                    detail="HTTPS bağlantısı yok, HTTP üzerinden erişildi",
                    latency_ms=round(latency, 1)
                ), status_code
        except Exception:
            pass
        latency = (time.monotonic() - start) * 1000
        return CheckItem(
            label="HTTP Erişim",
            status="error",
            value="Bağlantı kurulamadı",
            detail="Siteye HTTP/HTTPS üzerinden ulaşılamıyor",
            latency_ms=round(latency, 1)
        ), None

    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return CheckItem(
            label="HTTP Erişim",
            status="error",
            value="Hata",
            detail=f"Bağlantı hatası: {str(e)[:80]}",
            latency_ms=round(latency, 1)
        ), None


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.post("/", response_model=QuickCheckResponse)
@limiter.limit("20/minute")
async def quick_check(request: Request, payload: QuickCheckRequest):
    domain = validate_domain(payload.domain)

    # Tüm kontrolleri paralel çalıştır
    whois_task = do_whois(domain)
    ns_task = do_dns_ns(domain)
    a_task = do_dns_a(domain)
    mx_task = do_dns_mx(domain)
    ssl_task = do_ssl(domain)
    http_task = do_http(domain)

    whois_r, ns_r, a_r, mx_r, ssl_r, (http_r, http_code) = await asyncio.gather(
        whois_task, ns_task, a_task, mx_task, ssl_task, http_task
    )

    checks = [whois_r, ns_r, a_r, mx_r, ssl_r, http_r]

    # HTTP ve SSL sağlıklıysa, DNS hataları gerçek sorun değil
    # (sunucunun bulunduğu ağdan DNS çözümlenemiyor olabilir ama site çalışıyor)
    http_healthy = http_r.status == "healthy"
    ssl_healthy = ssl_r.status in ("healthy", "warning")
    site_reachable = http_healthy and ssl_healthy

    # DNS hatalarını site erişilebilirse uyarıya indir
    if site_reachable:
        for c in [ns_r, a_r, mx_r]:
            if c.status == "error":
                c.status = "warning"
                c.detail = (c.detail or "") + " (site erişilebilir — bu sunucudan DNS çözümlenemedi)"

    statuses = [c.status for c in checks]
    if "error" in statuses:
        overall = "error"
    elif "warning" in statuses:
        overall = "warning"
    else:
        overall = "healthy"

    # Özet metin
    errors = [c.label for c in checks if c.status == "error"]
    warnings = [c.label for c in checks if c.status == "warning"]
    if errors:
        summary = f"Kritik sorun: {', '.join(errors)}"
    elif warnings and site_reachable:
        summary = f"Site erişilebilir — bazı DNS sorgularında uyarı var: {', '.join(warnings)}"
    elif warnings:
        summary = f"Dikkat: {', '.join(warnings)}"
    else:
        summary = "Tüm kontroller başarılı — sistem sağlıklı görünüyor"

    # Hata analizi
    error_analysis = None
    if http_code and http_code >= 400:
        raw = analyze_error(http_code)
        if raw:
            error_analysis = ErrorAnalysis(**raw)

    return QuickCheckResponse(
        domain=domain,
        checks=checks,
        overall=overall,
        summary=summary,
        error_analysis=error_analysis,
        http_status=http_code,
    )
