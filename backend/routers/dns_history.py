import asyncio
import os
import re
import socket
import time
from datetime import datetime, timezone
from typing import Optional

import dns.resolver
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/dns-history", tags=["dns-history"])

PUBLIC_DNS = ['8.8.8.8', '1.1.1.1']
ST_BASE = "https://api.securitytrails.com/v1"


def make_resolver():
    r = dns.resolver.Resolver(configure=False)
    r.nameservers = PUBLIC_DNS
    r.timeout = 4.0
    r.lifetime = 4.0
    return r


# ── WHOIS yardımcıları ────────────────────────────────────────────────────────

TR_TLDS = ('.com.tr', '.net.tr', '.org.tr', '.av.tr', '.biz.tr',
           '.info.tr', '.tv.tr', '.tel.tr', '.name.tr', '.gov.tr',
           '.edu.tr', '.mil.tr', '.k12.tr', '.pol.tr', '.web.tr', '.tr')

WHOIS_SERVERS = {
    'com': 'whois.verisign-grs.com', 'net': 'whois.verisign-grs.com',
    'org': 'whois.pir.org', 'io': 'whois.nic.io', 'co': 'whois.nic.co',
    'info': 'whois.afilias.net', 'biz': 'whois.biz', 'xyz': 'whois.nic.xyz',
    'online': 'whois.nic.online', 'site': 'whois.nic.site',
    'app': 'whois.nic.google', 'dev': 'whois.nic.google',
    'eu': 'whois.eu', 'de': 'whois.denic.de', 'fr': 'whois.nic.fr',
    'uk': 'whois.nic.uk', 'nl': 'whois.domain-registry.nl',
    'com.tr': 'whois.trabis.gov.tr', 'net.tr': 'whois.trabis.gov.tr',
    'org.tr': 'whois.trabis.gov.tr', 'gov.tr': 'whois.trabis.gov.tr',
    'edu.tr': 'whois.trabis.gov.tr', 'av.tr': 'whois.trabis.gov.tr',
    'biz.tr': 'whois.trabis.gov.tr', 'tr': 'whois.trabis.gov.tr',
}

CREATED_PATTERNS = [
    (re.compile(r'Created on[.\s]*:\s*(\d{4}-\w{3}-\d{2})\.?', re.I), '%Y-%b-%d'),
    (re.compile(r'(?:Creation Date|created(?:-date)?|Domain Create Date|registration time):\s*(\d{4}-\d{2}-\d{2})', re.I), '%Y-%m-%d'),
    (re.compile(r'(?:Creation Date|created):\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', re.I), '%Y-%m-%dT%H:%M:%S'),
    (re.compile(r'(?:Created On|registered):\s*(\d{2}-\w{3}-\d{4})', re.I), '%d-%b-%Y'),
]

EXPIRY_PATTERNS = [
    (re.compile(r'Expires on[.\s]*:\s*(\d{4}-\w{3}-\d{2})\.?', re.I), '%Y-%b-%d'),
    (re.compile(r'(?:Registry Expiry Date|Expiry Date|Expiration Date|paid-till|renewal-date):\s*(\d{4}-\d{2}-\d{2})', re.I), '%Y-%m-%d'),
    (re.compile(r'(?:Registry Expiry Date|Expiry Date|Expiration Date):\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', re.I), '%Y-%m-%dT%H:%M:%S'),
]

REGISTRAR_PATTERNS = [
    re.compile(r'Sponsoring Registrar:\s*(.+)', re.I),
    re.compile(r'registrar-name:\s*(.+)', re.I),
    re.compile(r'Organization Name\s*:\s*(.+)', re.I),
    re.compile(r'Registrar:\s*(.+\S)', re.I),
]


def _raw_whois(server: str, query: str, timeout: float = 8.0) -> str:
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


def _parse_date(raw: str, patterns) -> Optional[datetime]:
    for pattern, fmt in patterns:
        m = pattern.search(raw)
        if m:
            try:
                return datetime.strptime(m.group(1).strip()[:19], fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _parse_registrar(raw: str) -> str:
    for pattern in REGISTRAR_PATTERNS:
        m = pattern.search(raw)
        if m:
            return m.group(1).strip()[:80]
    return ""


def _whois_lookup(domain: str) -> dict:
    """WHOIS'ten kayıt tarihi, bitiş tarihi ve registrar'ı döndürür."""
    result = {'created': None, 'expires': None, 'registrar': ''}

    is_tr = any(domain.endswith(t) for t in TR_TLDS)
    parts = domain.split('.')
    if is_tr:
        server = 'whois.trabis.gov.tr'
    else:
        server = None
        if len(parts) >= 3:
            server = WHOIS_SERVERS.get('.'.join(parts[-2:]))
        if not server:
            server = WHOIS_SERVERS.get(parts[-1])
        if not server:
            try:
                resp = _raw_whois('whois.iana.org', parts[-1], 4.0)
                for line in resp.splitlines():
                    if line.lower().startswith('whois:'):
                        server = line.split(':', 1)[1].strip()
                        break
            except Exception:
                pass

    if not server:
        return result

    try:
        raw = _raw_whois(server, domain, 8.0)
        result['created'] = _parse_date(raw, CREATED_PATTERNS)
        result['expires'] = _parse_date(raw, EXPIRY_PATTERNS)
        result['registrar'] = _parse_registrar(raw)
    except Exception:
        pass

    return result


# ── Schemas ───────────────────────────────────────────────────────────────────

class NSEntry(BaseModel):
    nameservers: list[str]
    first_seen: str
    last_seen: str
    organizations: list[str] = []
    is_current: bool = False


class DNSHistoryRequest(BaseModel):
    domain: str


class DNSHistoryResponse(BaseModel):
    domain: str
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    registrar: Optional[str] = None
    current_ns: list[str] = []
    ns_history: list[NSEntry] = []
    has_api_key: bool = False
    message: str = ""


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/lookup", response_model=DNSHistoryResponse)
async def lookup_history(payload: DNSHistoryRequest):
    domain = payload.domain.strip().lower()
    domain = re.sub(r'^https?://', '', domain).split('/')[0].split('?')[0]

    if not domain:
        raise HTTPException(status_code=400, detail="Domain boş olamaz")
    if len(domain) > 253:
        raise HTTPException(status_code=400, detail="Domain çok uzun")
    if '\x00' in domain or '..' in domain:
        raise HTTPException(status_code=400, detail="Geçersiz domain")

    loop = asyncio.get_event_loop()

    # ── Mevcut NS (DNS sorgusu) ───────────────────────────────────────────────
    async def get_current_ns():
        try:
            resolver = make_resolver()
            answers = await loop.run_in_executor(None, lambda: resolver.resolve(domain, 'NS'))
            return sorted([str(r).rstrip('.') for r in answers])
        except Exception:
            return []

    # ── WHOIS ────────────────────────────────────────────────────────────────
    async def get_whois():
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, _whois_lookup, domain),
                timeout=12.0,
            )
        except Exception:
            return {'created': None, 'expires': None, 'registrar': ''}

    current_ns, whois = await asyncio.gather(get_current_ns(), get_whois())

    created_str = whois['created'].strftime('%d.%m.%Y') if whois['created'] else None
    expires_str = whois['expires'].strftime('%d.%m.%Y') if whois['expires'] else None

    # ── SecurityTrails NS geçmişi (varsa) ────────────────────────────────────
    st_key = os.getenv("SECURITYTRAILS_API_KEY", "").strip()
    ns_history: list[NSEntry] = []
    has_api_key = bool(st_key)

    if st_key:
        headers = {"apikey": st_key, "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{ST_BASE}/history/{domain}/dns/ns", headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    current_ns_set = set(current_ns)
                    for rec in data.get("records", []):
                        ns_vals = sorted([v.get("nameserver", "").rstrip('.') for v in rec.get("values", [])])
                        orgs = rec.get("organizations", [])
                        first = rec.get("first_seen", "")
                        last  = rec.get("last_seen", "")
                        is_cur = bool(set(ns_vals) & current_ns_set)
                        ns_history.append(NSEntry(
                            nameservers=ns_vals,
                            first_seen=_fmt_st_date(first),
                            last_seen=_fmt_st_date(last),
                            organizations=orgs,
                            is_current=is_cur,
                        ))
                elif r.status_code == 401:
                    has_api_key = False   # geçersiz key
        except Exception:
            pass

    # Geçmiş yoksa mevcut NS'i ekle
    if not ns_history and current_ns:
        ns_history = [NSEntry(
            nameservers=current_ns,
            first_seen="—",
            last_seen="Güncel",
            organizations=[],
            is_current=True,
        )]

    msg = f"{len(ns_history)} NS kaydı" if ns_history else "NS geçmişi bulunamadı"
    if not has_api_key:
        msg = "SecurityTrails API anahtarı eklenerek tam NS geçmişi görüntülenebilir"

    return DNSHistoryResponse(
        domain=domain,
        created_at=created_str,
        expires_at=expires_str,
        registrar=whois['registrar'] or None,
        current_ns=current_ns,
        ns_history=ns_history,
        has_api_key=has_api_key,
        message=msg,
    )


def _fmt_st_date(s: str) -> str:
    """2023-04-15 → 15.04.2023"""
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d.%m.%Y')
    except Exception:
        return s
