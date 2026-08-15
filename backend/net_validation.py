"""Ağ girdisi doğrulama — IP adresi veya hostname kabul eden uçların ortak kapısı.

`ip_lookup._validate_and_clean`'in eksiklerini kapatır: uzunluk sınırı (≤253),
null-byte reddi, IPv6'da `is_reserved`/`is_multicast` kontrolü.
"""
import ipaddress
import re

from fastapi import HTTPException

_DOMAIN_RE = re.compile(r'^([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$')
_MAX_HOST_LEN = 253


def validate_host(raw: str, *, allow_ip: bool = True, allow_private: bool = False) -> str:
    """Girdiyi doğrular ve temizlenmiş halini döndürür; geçersizse HTTPException(400).

    allow_ip=False      → yalnızca alan adı kabul edilir
    allow_private=False → özel/loopback/link-local/rezerve/multicast IP'ler reddedilir
    """
    if raw is None or '\x00' in raw:
        raise HTTPException(400, "Geçersiz girdi")

    q = raw.strip().lower()
    q = re.sub(r'^https?://', '', q)
    q = q.split('/')[0].split('?')[0].split('#')[0]
    # köşeli parantezli IPv6 gösterimi: [::1]
    q = q.strip('[]')

    if not q:
        raise HTTPException(400, "IP adresi veya alan adı zorunludur")

    if len(q) > _MAX_HOST_LEN:
        raise HTTPException(400, f"Girdi en fazla {_MAX_HOST_LEN} karakter olabilir")

    # IP adresi mi? (IPv4 + IPv6)
    try:
        ip = ipaddress.ip_address(q)
    except ValueError:
        ip = None

    if ip is not None:
        if not allow_ip:
            raise HTTPException(400, "IP adresi yerine alan adı girin")
        if not allow_private and (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            raise HTTPException(400, "Özel / yerel / rezerve IP adresleri sorgulanamaz")
        return str(ip)

    if _DOMAIN_RE.match(q):
        return q

    raise HTTPException(400, "Geçersiz IP adresi veya alan adı formatı")
