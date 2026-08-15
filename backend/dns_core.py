"""DNS çekirdeği — router'ların paylaştığı resolver fabrikaları ve async yol.

Kural (CLAUDE.md): DNS sorguları sistem resolver'ını atlar ve açık timeout ile
public resolver'lara gider — panel DNS teşhis aracı olduğundan yerel makinenin
önbelleğini/resolver'ını miras almamalıdır.

Async yol (`make_async_resolver` / `resolve_async`) çok sayıda eşzamanlı sorgu
açan araçlar içindir (DNS yayılma, RBL): senkron `resolve()` +
`run_in_executor(None, ...)` varsayılan thread havuzunu doldurup diğer
araçları bloklar; async resolver hiç thread tüketmez.
"""
import dns.asyncresolver
import dns.exception
import dns.resolver

DEFAULT_NAMESERVERS = ['8.8.8.8', '1.1.1.1']
DEFAULT_TIMEOUT = 3.0  # saniye


def make_resolver(nameservers=None, timeout=None) -> dns.resolver.Resolver:
    """Senkron resolver — run_in_executor içinde kullanılır."""
    r = dns.resolver.Resolver(configure=False)
    r.nameservers = list(nameservers or DEFAULT_NAMESERVERS)
    t = DEFAULT_TIMEOUT if timeout is None else float(timeout)
    r.timeout = t
    r.lifetime = t
    return r


def make_async_resolver(nameservers=None, timeout=None) -> dns.asyncresolver.Resolver:
    r = dns.asyncresolver.Resolver(configure=False)
    r.nameservers = list(nameservers or DEFAULT_NAMESERVERS)
    t = DEFAULT_TIMEOUT if timeout is None else float(timeout)
    r.timeout = t
    r.lifetime = t
    return r


def classify_dns_error(exc: Exception) -> tuple[str, str]:
    """Tek tip istisna haritası: (durum_kodu, Türkçe mesaj).

    Durum kodları: nxdomain | no_answer | no_nameservers | timeout | error
    """
    if isinstance(exc, dns.resolver.NXDOMAIN):
        return 'nxdomain', 'Alan adı bulunamadı (NXDOMAIN)'
    if isinstance(exc, dns.resolver.NoAnswer):
        return 'no_answer', 'Bu kayıt tipi için yanıt yok'
    if isinstance(exc, dns.resolver.NoNameservers):
        return 'no_nameservers', 'Ad sunucuları yanıt vermedi'
    if isinstance(exc, dns.exception.Timeout):
        return 'timeout', 'DNS sorgusu zaman aşımına uğradı'
    return 'error', f'DNS hatası: {exc}'


def _format_rdata(rdata, rtype: str) -> str:
    if rtype == 'TXT':
        return ' '.join(p.decode('utf-8', errors='replace') for p in rdata.strings)
    if rtype == 'MX':
        return f'{rdata.preference} {str(rdata.exchange).rstrip(".")}'
    return str(rdata).rstrip('.')


async def resolve_async(domain: str, rtype: str, *,
                        nameservers=None, timeout=None, semaphore=None) -> dict:
    """Tek async sorgu. İstisna FIRLATMAZ; sonucu sözlük olarak döner:

    { 'status': 'found' | classify_dns_error kodu,
      'records': list[str], 'ttl': int|None, 'error': str|None }
    """
    resolver = make_async_resolver(nameservers, timeout)

    async def _do():
        answers = await resolver.resolve(domain, rtype)
        records = sorted(_format_rdata(r, rtype) for r in answers)
        ttl = answers.rrset.ttl if answers.rrset else None
        return {'status': 'found', 'records': records, 'ttl': ttl, 'error': None}

    try:
        if semaphore is not None:
            async with semaphore:
                return await _do()
        return await _do()
    except Exception as exc:
        status, msg = classify_dns_error(exc)
        return {'status': status, 'records': [], 'ttl': None, 'error': msg}
