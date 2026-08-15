"""E-posta kimlik doğrulama kayıtları için YAPISAL parser'lar.

dns_toolbox'taki analyze_* fonksiyonları birer formatlayıcıdır ve buradaki
parser'ları çağırır; mail_health router'ı ise aynı parser'ların yapısal
çıktısını puanlamada kullanır. Metin biçimlendirme burada YAPILMAZ.
"""


def parse_spf(txt: str) -> dict:
    """SPF kaydını yapısal olarak ayrıştırır.

    policy: 'all' mekanizması KÜÇÜK HARFE normalize edilir ('-ALL' → '-all').
    Eski analyze_spf ham token ile map'e bakıyordu; '-ALL' yazan kayıt
    "Politika bulunamadı" dönüyordu — normalizasyon bu bug'ı kapatır.
    """
    parts = txt.split()
    policy_token = next((p for p in parts if p.lower().endswith('all')), None)
    return {
        'policy': policy_token.lower() if policy_token else None,
        'includes': [p.split(':', 1)[1] for p in parts if p.startswith('include:')],
        'ips': [p.split(':', 1)[1] for p in parts if p.startswith('ip4:') or p.startswith('ip6:')],
        'redirects': [p.split('=', 1)[1] for p in parts if p.startswith('redirect=')],
    }


def parse_dmarc(txt: str) -> dict:
    """DMARC kaydını tag sözlüğüne ayrıştırır."""
    tags = {}
    for part in txt.split(';'):
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            tags[k.strip().lower()] = v.strip()
    return {
        'tags': tags,
        'policy': tags.get('p', 'none'),
        'subdomain_policy': tags.get('sp', ''),
        'pct': tags.get('pct', '100'),
        'rua': tags.get('rua', ''),
    }


def parse_dkim(txt: str) -> dict:
    """DKIM TXT kaydını ayrıştırır; anahtar boyutunu base64 uzunluğundan tahmin eder."""
    tags = {}
    for part in txt.split(';'):
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            tags[k.strip().lower()] = v.strip()

    pub = tags.get('p', '')
    clean = pub.replace(' ', '').replace('\n', '')
    key_bits = (len(clean) * 3 // 4) * 8 if clean else 0

    return {
        'tags': tags,
        'version': tags.get('v', 'DKIM1'),
        'algorithm': tags.get('k', 'rsa').upper(),
        'public_key': pub,
        'key_bits': key_bits,
        'service': tags.get('s', ''),
        'valid': bool(clean),
    }
