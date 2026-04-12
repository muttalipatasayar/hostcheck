import asyncio
import time
from typing import Optional

import dns.resolver
import dns.reversename
import dns.rdatatype
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/dns-toolbox", tags=["dns-toolbox"])

PUBLIC_DNS = ['8.8.8.8', '1.1.1.1', '9.9.9.9']
DNS_TIMEOUT = 5.0


def make_resolver() -> dns.resolver.Resolver:
    r = dns.resolver.Resolver(configure=False)
    r.nameservers = PUBLIC_DNS
    r.timeout = DNS_TIMEOUT
    r.lifetime = DNS_TIMEOUT
    return r


# ── Schemas ───────────────────────────────────────────────────────────────────

class DNSRecord(BaseModel):
    value: str
    ttl: Optional[int] = None
    priority: Optional[int] = None   # MX
    extra: Optional[str] = None      # ek bilgi (SOA alanları vb.)


class DNSQueryRequest(BaseModel):
    domain: str
    record_type: str        # A AAAA CNAME MX NS TXT SOA PTR SPF DMARC DKIM
    selector: Optional[str] = None   # Sadece DKIM için


class DNSQueryResponse(BaseModel):
    domain: str
    queried_domain: str            # _dmarc.x, arpa vb. olabilir
    record_type: str
    records: list[DNSRecord]
    status: str                    # found | not_found | error
    message: str
    nameservers: list[str]
    query_ms: Optional[float] = None
    analysis: Optional[str] = None


# ── Analiz fonksiyonları ──────────────────────────────────────────────────────

def analyze_spf(txt: str) -> str:
    parts = txt.split()
    policy = next((p for p in parts if p.lower().endswith('all')), None)
    policy_map = {
        '-all': '❌ Sıkı (Fail) — yetkisiz sunuculardan gelen e-postalar reddedilir',
        '~all': '⚠ Yumuşak (SoftFail) — yetkisiz e-postalar spam olarak işaretlenir',
        '+all': '🔓 Açık (Pass) — tüm sunuculardan gönderime izin verilir (zayıf ayar)',
        '?all': 'ℹ Nötr — politika belirtilmemiş',
    }
    result = policy_map.get(policy, 'Politika mekanizması bulunamadı')
    includes = [p for p in parts if p.startswith('include:')]
    redirects = [p for p in parts if p.startswith('redirect=')]
    ips = [p for p in parts if p.startswith('ip4:') or p.startswith('ip6:')]
    details = []
    if includes:
        details.append(f"İzin verilen servisler: {', '.join(i.split(':',1)[1] for i in includes)}")
    if ips:
        details.append(f"İzin verilen IP'ler: {', '.join(i.split(':',1)[1] for i in ips)}")
    if redirects:
        details.append(f"Yönlendirme: {redirects[0].split('=',1)[1]}")
    return result + (' | ' + ' | '.join(details) if details else '')


def analyze_dmarc(txt: str) -> str:
    tags = {}
    for part in txt.split(';'):
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            tags[k.strip().lower()] = v.strip()

    p = tags.get('p', 'none')
    sp = tags.get('sp', '')
    pct = tags.get('pct', '100')
    policy_map = {
        'none':       '👁 İzleme (none) — başarısız e-postalar yine de iletilir, sadece rapor alınır',
        'quarantine': '📦 Karantina — başarısız e-postalar spam klasörüne gönderilir',
        'reject':     '🚫 Ret (reject) — başarısız e-postalar tamamen reddedilir',
    }
    lines = [policy_map.get(p, f'Politika: {p}')]
    if sp:
        lines.append(f"Alt alan politikası: {sp}")
    if pct != '100':
        lines.append(f"Uygulama oranı: %{pct}")
    rua = tags.get('rua', '')
    if rua:
        lines.append(f"Toplam rapor adresi: {rua}")
    return ' | '.join(lines)


def analyze_dkim(txt: str, selector: str) -> str:
    tags = {}
    for part in txt.split(';'):
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            tags[k.strip().lower()] = v.strip()
    ver = tags.get('v', 'DKIM1')
    alg = tags.get('k', 'rsa').upper()
    pub = tags.get('p', '')

    if not pub:
        return f"❌ Selector '{selector}' geçersiz — public key (p=) eksik veya anahtar iptal edilmiş"

    # Base64 uzunluğundan key boyutunu tahmin et
    clean = pub.replace(' ', '').replace('\n', '')
    key_bytes = len(clean) * 3 // 4
    key_bits  = key_bytes * 8

    if key_bits >= 2048:
        health = f"✅ DKIM geçerli ve sağlıklı — güçlü anahtar (~{key_bits} bit)"
    elif key_bits >= 1024:
        health = f"⚠ DKIM geçerli fakat anahtar boyutu küçük (~{key_bits} bit, önerilen: 2048+)"
    else:
        health = f"❌ DKIM anahtar boyutu çok küçük (~{key_bits} bit) — güvenlik riski"

    service = tags.get('s', '')
    svc_str = f" | Servis: {service}" if service and service != '*' else ''
    return f"{health} | Selector: {selector} | Versiyon: {ver} | Algoritma: {alg}{svc_str}"


def analyze_mx(records: list[DNSRecord]) -> str:
    if not records:
        return 'MX kaydı yok — bu alan adına e-posta gönderilemez'
    providers = []
    for r in records:
        v = r.value.lower()
        if 'google' in v or 'googlemail' in v:
            providers.append('Google Workspace')
        elif 'outlook' in v or 'microsoft' in v or 'protection.outlook' in v:
            providers.append('Microsoft 365 / Exchange')
        elif 'yandex' in v:
            providers.append('Yandex Mail')
        elif 'zoho' in v:
            providers.append('Zoho Mail')
        elif 'mimecast' in v:
            providers.append('Mimecast')
        elif 'pphosted' in v or 'proofpoint' in v:
            providers.append('Proofpoint')
    if providers:
        unique = list(dict.fromkeys(providers))
        return f"E-posta sağlayıcısı: {', '.join(unique)}"
    return f"{len(records)} MX kaydı bulundu"


# ── Sorgu mantığı ─────────────────────────────────────────────────────────────

def _query_sync(queried_domain: str, rtype: str) -> tuple[list[DNSRecord], int]:
    """Senkron DNS sorgusu — run_in_executor içinde çağrılır."""
    resolver = make_resolver()
    start = time.monotonic()

    answers = resolver.resolve(queried_domain, rtype)
    elapsed = round((time.monotonic() - start) * 1000, 1)

    records: list[DNSRecord] = []
    ttl = answers.rrset.ttl if answers.rrset else None

    for rdata in answers:
        if rtype == 'MX':
            records.append(DNSRecord(
                value=str(rdata.exchange).rstrip('.'),
                ttl=ttl,
                priority=rdata.preference,
            ))
        elif rtype == 'SOA':
            records.append(DNSRecord(
                value=str(rdata.mname).rstrip('.'),
                ttl=ttl,
                extra=(
                    f"Sorumlu: {str(rdata.rname).rstrip('.')} | "
                    f"Seri: {rdata.serial} | "
                    f"Yenile: {rdata.refresh}s | "
                    f"Yeniden Dene: {rdata.retry}s | "
                    f"Sona Erme: {rdata.expire}s | "
                    f"Min TTL: {rdata.minimum}s"
                ),
            ))
        elif rtype == 'TXT':
            records.append(DNSRecord(
                value=' '.join(p.decode('utf-8', errors='replace') for p in rdata.strings),
                ttl=ttl,
            ))
        elif rtype in ('PTR', 'CNAME', 'NS'):
            records.append(DNSRecord(value=str(rdata.target).rstrip('.'), ttl=ttl))
        else:
            records.append(DNSRecord(value=str(rdata), ttl=ttl))

    if rtype == 'MX':
        records.sort(key=lambda r: r.priority or 0)

    return records, elapsed


async def _run_query(queried_domain: str, rtype: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _query_sync, queried_domain, rtype)


# ── Endpoint ──────────────────────────────────────────────────────────────────

SUPPORTED = {'A', 'AAAA', 'CNAME', 'MX', 'NS', 'TXT', 'SOA', 'PTR', 'SPF', 'DMARC', 'DKIM', 'DNSSEC'}

# Selector bulunamazsa sırayla denenir
COMMON_SELECTORS = [
    'default', 'google', 'mail', 'dkim', 'k1', 'k2',
    's1', 's2', 'selector1', 'selector2',
    'mandrill', 'mailchimp', 'mg', 'sendgrid',
    'pm', 'smtp', 'email', 'key1', 'sig1',
]


def _try_dkim_selector(domain: str, selector: str) -> tuple[list[DNSRecord], int] | None:
    """Tek bir selector dener. Bulunamazsa None döner."""
    queried = f'{selector}._domainkey.{domain}'
    try:
        records, ms = _query_sync(queried, 'TXT')
        if records:
            return records, ms
    except Exception:
        pass
    return None


async def _dkim_auto_discover(domain: str) -> tuple[list[DNSRecord], str, int] | None:
    """Yaygın selectorları paralel dener, ilk bulunanı döner."""
    loop = asyncio.get_event_loop()

    async def try_one(sel):
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _try_dkim_selector, domain, sel),
                timeout=4.0,
            )
            if result:
                return sel, result
        except Exception:
            pass
        return None

    # 5'er batch halinde dene — hepsini aynı anda açmak yerine
    for i in range(0, len(COMMON_SELECTORS), 5):
        batch = COMMON_SELECTORS[i:i+5]
        tasks = [try_one(s) for s in batch]
        results = await asyncio.gather(*tasks)
        for res in results:
            if res:
                sel, (recs, ms) = res
                return recs, sel, ms
    return None


@router.post("/query", response_model=DNSQueryResponse)
async def dns_query(payload: DNSQueryRequest):
    domain = payload.domain.strip().lower()
    domain = __import__('re').sub(r'^https?://', '', domain).split('/')[0]
    rtype = payload.record_type.upper()

    if rtype not in SUPPORTED:
        raise HTTPException(status_code=400, detail=f"Desteklenmeyen kayıt tipi: {rtype}")
    if not domain:
        raise HTTPException(status_code=400, detail="Domain boş olamaz")

    # ── DKIM — özel akış ──────────────────────────────────────────────────────
    if rtype == 'DKIM':
        selector = (payload.selector or '').strip().lower()

        if selector:
            # Belirli selector sorgusu
            queried_domain = f'{selector}._domainkey.{domain}'
            try:
                records, query_ms = await asyncio.wait_for(
                    _run_query(queried_domain, 'TXT'),
                    timeout=8.0,
                )
            except asyncio.TimeoutError:
                return DNSQueryResponse(
                    domain=domain, queried_domain=queried_domain, record_type=rtype,
                    records=[], status='error', message='Zaman aşımı',
                    nameservers=PUBLIC_DNS,
                )
            except Exception:
                return DNSQueryResponse(
                    domain=domain, queried_domain=queried_domain, record_type=rtype,
                    records=[], status='not_found',
                    message=f"'{selector}' selector'ı için DKIM kaydı bulunamadı",
                    nameservers=PUBLIC_DNS,
                )
            analysis = analyze_dkim(records[0].value, selector) if records else None
            return DNSQueryResponse(
                domain=domain, queried_domain=queried_domain, record_type=rtype,
                records=records,
                status='found' if records else 'not_found',
                message=f'{len(records)} kayıt bulundu' if records else 'Kayıt yok',
                nameservers=PUBLIC_DNS, query_ms=query_ms, analysis=analysis,
            )
        else:
            # Auto-discovery
            result = await _dkim_auto_discover(domain)
            if result:
                records, found_sel, query_ms = result
                queried_domain = f'{found_sel}._domainkey.{domain}'
                analysis = analyze_dkim(records[0].value, found_sel) if records else None
                return DNSQueryResponse(
                    domain=domain, queried_domain=queried_domain, record_type=rtype,
                    records=records, status='found',
                    message=f"'{found_sel}' selector'ı ile DKIM kaydı bulundu",
                    nameservers=PUBLIC_DNS, query_ms=query_ms, analysis=analysis,
                )
            return DNSQueryResponse(
                domain=domain, queried_domain=f'*._domainkey.{domain}', record_type=rtype,
                records=[], status='not_found',
                message='Yaygın DKIM selector\'ları denendi, kayıt bulunamadı. Selector\'ı manuel girin.',
                nameservers=PUBLIC_DNS,
            )

    # ── DNSSEC ────────────────────────────────────────────────────────────────
    if rtype == 'DNSSEC':
        queried_domain = domain
        records = []
        analysis_parts = []
        total_ms = 0

        # DS kaydı — üst zone'da imza referansı
        try:
            ds_recs, ms = await asyncio.wait_for(
                _run_query(domain, 'DS'), timeout=6.0)
            total_ms += ms
            for r in ds_recs:
                records.append(DNSRecord(value=r.value, ttl=r.ttl, extra='DS — Delegation Signer'))
            analysis_parts.append(f'✅ DS kaydı mevcut ({len(ds_recs)} adet) — üst zone imzası var')
        except asyncio.TimeoutError:
            analysis_parts.append('⏱ DS sorgusu zaman aşımı')
        except Exception:
            analysis_parts.append('❌ DS kaydı yok — DNSSEC üst zonede etkin değil ya da delegasyon yok')

        # DNSKEY — zone imzalama anahtarları
        try:
            key_recs, ms = await asyncio.wait_for(
                _run_query(domain, 'DNSKEY'), timeout=6.0)
            total_ms += ms
            for r in key_recs:
                records.append(DNSRecord(value=r.value[:80] + '…' if len(r.value) > 80 else r.value,
                                         ttl=r.ttl, extra='DNSKEY — Zone İmzalama Anahtarı'))
            analysis_parts.append(f'✅ DNSKEY mevcut ({len(key_recs)} anahtar) — zone imzalanmış')
        except asyncio.TimeoutError:
            analysis_parts.append('⏱ DNSKEY sorgusu zaman aşımı')
        except Exception:
            analysis_parts.append('❌ DNSKEY yok — zone imzalanmamış')

        # RRSIG — imza kaydı (A üzerinden kontrol)
        try:
            rrsig_recs, ms = await asyncio.wait_for(
                _run_query(domain, 'RRSIG'), timeout=6.0)
            total_ms += ms
            for r in rrsig_recs:
                records.append(DNSRecord(value=r.value[:80] + '…' if len(r.value) > 80 else r.value,
                                         ttl=r.ttl, extra='RRSIG — Kayıt İmzası'))
            analysis_parts.append(f'✅ RRSIG imzası mevcut ({len(rrsig_recs)} adet)')
        except asyncio.TimeoutError:
            analysis_parts.append('⏱ RRSIG sorgusu zaman aşımı')
        except Exception:
            analysis_parts.append('❌ RRSIG yok — kayıtlar imzalanmamış')

        dnssec_active = any('✅' in p for p in analysis_parts)
        status = 'found' if dnssec_active else 'not_found'
        msg = 'DNSSEC etkin — zone imzalanmış' if dnssec_active else 'DNSSEC etkin değil veya eksik yapılandırılmış'

        return DNSQueryResponse(
            domain=domain, queried_domain=domain, record_type='DNSSEC',
            records=records, status=status, message=msg,
            nameservers=PUBLIC_DNS,
            query_ms=round(total_ms, 1),
            analysis=' | '.join(analysis_parts),
        )

    # ── Diğer tipler ──────────────────────────────────────────────────────────
    queried_domain = domain
    dns_rtype = rtype

    if rtype == 'SPF':
        dns_rtype = 'TXT'
    elif rtype == 'DMARC':
        dns_rtype = 'TXT'
        queried_domain = f'_dmarc.{domain}'
    elif rtype == 'PTR':
        try:
            queried_domain = str(dns.reversename.from_address(domain))
        except Exception:
            raise HTTPException(status_code=400, detail="PTR için geçerli bir IP adresi girin")

    try:
        records, query_ms = await asyncio.wait_for(
            _run_query(queried_domain, dns_rtype),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        return DNSQueryResponse(
            domain=domain, queried_domain=queried_domain, record_type=rtype,
            records=[], status='error', message='DNS sorgusu zaman aşımına uğradı (10s)',
            nameservers=PUBLIC_DNS,
        )
    except dns.resolver.NXDOMAIN:
        return DNSQueryResponse(
            domain=domain, queried_domain=queried_domain, record_type=rtype,
            records=[], status='not_found',
            message=f'{queried_domain} için {rtype} kaydı bulunamadı',
            nameservers=PUBLIC_DNS,
        )
    except dns.resolver.NoAnswer:
        return DNSQueryResponse(
            domain=domain, queried_domain=queried_domain, record_type=rtype,
            records=[], status='not_found',
            message=f'{domain} için {rtype} kaydı tanımlanmamış',
            nameservers=PUBLIC_DNS,
        )
    except Exception as e:
        return DNSQueryResponse(
            domain=domain, queried_domain=queried_domain, record_type=rtype,
            records=[], status='error',
            message=f'Sorgu hatası: {type(e).__name__}',
            nameservers=PUBLIC_DNS,
        )

    if rtype == 'SPF':
        records = [r for r in records if r.value.lower().startswith('v=spf1')]
        if not records:
            return DNSQueryResponse(
                domain=domain, queried_domain=queried_domain, record_type=rtype,
                records=[], status='not_found',
                message=f'{domain} için SPF kaydı (v=spf1) bulunamadı',
                nameservers=PUBLIC_DNS, query_ms=query_ms,
            )

    analysis = None
    if rtype == 'SPF' and records:
        analysis = analyze_spf(records[0].value)
    elif rtype == 'DMARC' and records:
        analysis = analyze_dmarc(records[0].value)
    elif rtype == 'MX':
        analysis = analyze_mx(records)

    return DNSQueryResponse(
        domain=domain, queried_domain=queried_domain, record_type=rtype,
        records=records, status='found',
        message=f'{len(records)} kayıt bulundu',
        nameservers=PUBLIC_DNS, query_ms=query_ms, analysis=analysis,
    )
