"""Ağ girdisi doğrulama — IP adresi veya hostname kabul eden uçların ortak kapısı.

`ip_lookup._validate_and_clean`'in eksiklerini kapatır: uzunluk sınırı (≤253),
null-byte reddi, IPv6'da `is_reserved`/`is_multicast` kontrolü.
"""
import ipaddress
import re
import urllib.parse

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


# ── Çözümleme sonrası IP doğrulaması (SSRF kapısı) ────────────────────────────
#
# `validate_host` / `validate_domain` yalnızca STRING doğrular: IP
# literallerini reddeder ama alan adının hangi IP'ye çözüldüğüne bakmaz.
# "127.0.0.1.nip.io" ve "localtest.me" gibi isimler bu kontrolden geçip
# 127.0.0.1'e çözülür — panel iç ağa yönlendirilebilir.
#
# Bu yüzden DIŞARI BAĞLANAN her uç, hedefi burada çözüp dönen IP'ye
# BAĞLANMALIDIR. IP'ye pinlemek, doğrulama ile bağlantı arasındaki DNS
# rebinding penceresini de kapatır (aksi hâlde işletim sistemi ikinci kez
# çözer ve arada kayıt değişebilir).

import asyncio
import socket

_RESOLVE_TIMEOUT = 5.0


def is_public_ip(ip) -> bool:
    """Adres panelin dışarı çıkabileceği bir genel adres mi?

    IPv4-mapped IPv6 (::ffff:127.0.0.1) sarmalı açılarak kontrol edilir —
    aksi hâlde loopback bu gösterimle gizlenebilir.
    """
    if isinstance(ip, str):
        ip = ipaddress.ip_address(ip)
    mapped = getattr(ip, 'ipv4_mapped', None)
    if mapped is not None:
        ip = mapped
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def resolve_public_ips(host: str, port: int = 0) -> list[str]:
    """Hostu çözer ve TÜM adreslerinin genel olduğunu doğrular.

    Tek bir adres bile özel/yerel ise tamamı reddedilir: bir isim hem genel
    hem yerel adres yayınlayarak (DNS round-robin) kontrolü atlatamasın.

    Dönen liste bağlantı için kullanılmalıdır — hostu yeniden çözmeyin.
    Bloklayıcıdır; `resolve_public_ips_async` üzerinden çağırın.
    """
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if not is_public_ip(literal):
            raise HTTPException(400, "Özel / yerel / rezerve adresler sorgulanamaz")
        return [str(literal)]

    try:
        infos = socket.getaddrinfo(host, port or None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise HTTPException(400, f"Alan adı çözümlenemedi: {host}")
    except OSError:
        raise HTTPException(400, f"Alan adı çözümlenemedi: {host}")

    ips: list[str] = []
    for info in infos:
        addr = info[4][0]
        if addr not in ips:
            ips.append(addr)

    if not ips:
        raise HTTPException(400, f"Alan adı çözümlenemedi: {host}")

    for addr in ips:
        if not is_public_ip(addr):
            raise HTTPException(
                400,
                "Hedef özel / yerel bir adrese çözümleniyor — bu adresler sorgulanamaz",
            )
    return ips


async def resolve_public_ips_async(host: str, port: int = 0) -> list[str]:
    """`resolve_public_ips`'in event loop'u bloklamayan sarmalı."""
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, resolve_public_ips, host, port),
            timeout=_RESOLVE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, f"Alan adı çözümlemesi zaman aşımına uğradı: {host}")


async def assert_public_target(host: str, port: int = 0) -> str:
    """Hedefi doğrular ve bağlanılacak İLK genel IP'yi döndürür."""
    return (await resolve_public_ips_async(host, port))[0]


# ── Playwright route guard (tarayıcı tabanlı uçların SSRF kapısı) ─────────────
#
# `--host-resolver-rules` YALNIZCA ana hostu pinler. Sayfa bir yönlendirme,
# iframe veya alt kaynak ile başka bir isme gidip oradan iç ağa ulaşabilir —
# ve sonuç (PNG, ölçüm, DOM) kullanıcıya döner. Bu kanca tarayıcının yaptığı
# HER isteği süzer.
#
# `screenshot.py` ve `routers/site_speed/engine.py` ikisi de buradan import
# eder. İki ayrı kopya tutulsaydı biri yamalanıp diğeri unutulduğunda sessiz
# bir SSRF açığı kalırdı.

def make_playwright_route_guard():
    """Genel olmayan adrese giden her isteği iptal eden Playwright kancası.

    Çözümlemeler ÇAĞRI BAŞINA önbelleklenir — önbellek kapanışta tutulur,
    modül seviyesinde DEĞİL: aynı executor'da iki ölçüm paralel çalışabilir
    ve paylaşılan bir sözlük yarış durumu üretirdi.

    Kanca Playwright'ın kendi thread'inde çalıştığından bloklayıcı
    `getaddrinfo` burada güvenlidir (event loop'u tutmaz).
    """
    cache: dict[str, bool] = {}

    def guard(route, request):
        try:
            host = urllib.parse.urlparse(request.url).hostname or ""
            if not host:
                route.abort()
                return
            allowed = cache.get(host)
            if allowed is None:
                try:
                    ipaddress.ip_address(host)
                    addrs = [host]
                except ValueError:
                    addrs = [i[4][0] for i in
                             socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)]
                allowed = bool(addrs) and all(is_public_ip(a) for a in addrs)
                cache[host] = allowed
            if allowed:
                route.continue_()
            else:
                route.abort()
        except Exception:
            # Şüphe hâlinde reddet — çözümlenemeyen host geçirilmez
            route.abort()

    return guard
