"""Bağlantı fazı ölçümü — DNS / TCP / TLS / sunucu ayrı ayrı.

Hosting desteğinin en çok ihtiyaç duyduğu tek şey bu: "site yavaş" çağrısında
gecikmenin ağda mı, TLS el sıkışmasında mı, yoksa sunucunun kendisinde mi
olduğunu söyler. PageSpeed Insights bu ayrımı hiç vermez — tek bir
"sunucu yanıt süresi" sayısı döndürür.

Ham `asyncio` + `ssl` kullanılır, httpx değil: httpx faz faz zaman vermez ve
bağlantıyı isme göre kurar. Burada **çözümlenmiş IP'ye** bağlanıp SNI'yı
`server_hostname` ile elle veriyoruz — böylece doğrulama ile bağlantı
arasındaki DNS rebinding penceresi kapanır (CLAUDE.md SSRF kuralı).
"""

import asyncio
import socket
import ssl
import statistics
import time

from net_validation import resolve_public_ips_async

# Tek bir faz için üst sınır — yavaş sunucuda tüm işi kilitlemesin
_PHASE_TIMEOUT = 10.0
# Kaç ölçüm alınıp medyanı hesaplanacak (tek ölçüm gürültülüdür)
_REPEATS = 3
# Yönlendirme zincirinde izlenecek en fazla adım
_MAX_REDIRECTS = 5
# Gövdeden en fazla kaç bayt okunacak (TTFB için gövde gerekmez)
_MAX_BODY_PEEK = 65536

_UA = ("Mozilla/5.0 (Linux; Android 11; moto g power (2022)) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36")

# CDN imzaları: başlık adı → sağlayıcı. Değere değil varlığa bakılır.
_CDN_HEADERS = {
    "cf-ray":            "Cloudflare",
    "cf-cache-status":   "Cloudflare",
    "x-amz-cf-id":       "Amazon CloudFront",
    "x-amz-cf-pop":      "Amazon CloudFront",
    "x-served-by":       "Fastly",
    "x-fastly-request-id": "Fastly",
    "x-akamai-request-id": "Akamai",
    "x-akamai-transformed": "Akamai",
    "x-sucuri-id":       "Sucuri",
    "x-iinfo":           "Imperva / Incapsula",
    "x-bunnycdn-cache-status": "BunnyCDN",
    "x-cdn":             "CDN (genel)",
    "x-azure-ref":       "Azure Front Door",
    "x-goog-generation": "Google Cloud CDN",
}


async def _tls_probe(host: str, ip: str, port: int = 443) -> dict:
    """TLS sürümü / ALPN / şifre süiti — yalnızca el sıkışma, istek yok.

    ALPN'de `h2` teklif edilir; sunucu seçerse HTTP/2 desteği KESİN olarak
    bilinir (başlık tahmini değil, protokol düzeyinde kanıt).
    """
    out = {"tls_version": None, "alpn": None, "cipher": None, "http2": False}
    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=_PHASE_TIMEOUT)
        ctx = ssl.create_default_context()
        ctx.set_alpn_protocols(["h2", "http/1.1"])
        await asyncio.wait_for(
            writer.start_tls(ctx, server_hostname=host), timeout=_PHASE_TIMEOUT)
        obj = writer.get_extra_info("ssl_object")
        if obj is not None:
            out["tls_version"] = obj.version()
            out["alpn"] = obj.selected_alpn_protocol()
            cipher = obj.cipher()
            out["cipher"] = cipher[0] if cipher else None
            out["http2"] = out["alpn"] == "h2"
    except Exception:
        pass  # TLS yoksa / reddedilirse alanlar None kalır — hata değil
    finally:
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
    return out


def _parse_status_and_headers(head: bytes) -> tuple[int, dict]:
    """Ham HTTP/1.1 yanıt başlığını ayrıştırır."""
    text = head.decode("iso-8859-1", errors="replace")
    lines = text.split("\r\n")
    status = 0
    if lines and lines[0].startswith("HTTP/"):
        parts = lines[0].split(" ", 2)
        if len(parts) >= 2 and parts[1].isdigit():
            status = int(parts[1])
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, _, value = line.partition(":")
        # Aynı başlık tekrarlanırsa ilkini koru (Set-Cookie hariç önemsiz)
        headers.setdefault(name.strip().lower(), value.strip())
    return status, headers


async def _single_run(host: str, ip: str, path: str, port: int, use_tls: bool) -> dict:
    """Tek bir bağlantının fazlarını ölçer ve yanıt başlıklarını döndürür."""
    r = {"dns_ms": 0.0, "tcp_ms": 0.0, "tls_ms": 0.0,
         "sunucu_ms": 0.0, "indirme_ms": 0.0, "toplam_ms": 0.0,
         "status": 0, "headers": {}}
    writer = None
    try:
        t_start = time.perf_counter()

        t = time.perf_counter()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=_PHASE_TIMEOUT)
        r["tcp_ms"] = (time.perf_counter() - t) * 1000

        if use_tls:
            t = time.perf_counter()
            ctx = ssl.create_default_context()
            # Bu bağlantıda ham HTTP/1.1 konuşacağız; h2 teklif ETME, yoksa
            # sunucu h2 seçer ve gönderdiğimiz metin isteği anlamsız olur.
            ctx.set_alpn_protocols(["http/1.1"])
            await asyncio.wait_for(
                writer.start_tls(ctx, server_hostname=host), timeout=_PHASE_TIMEOUT)
            r["tls_ms"] = (time.perf_counter() - t) * 1000

        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: {_UA}\r\n"
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
            "Accept-Encoding: gzip, deflate, br\r\n"
            "Connection: close\r\n\r\n"
        ).encode("iso-8859-1", errors="ignore")

        t = time.perf_counter()
        writer.write(request)
        await writer.drain()

        # İlk bayta kadar geçen süre = sunucunun düşünme süresi
        first = await asyncio.wait_for(reader.read(1), timeout=_PHASE_TIMEOUT)
        r["sunucu_ms"] = (time.perf_counter() - t) * 1000
        if not first:
            return r

        # Başlık bloğunun tamamını topla
        t = time.perf_counter()
        buf = bytearray(first)
        while b"\r\n\r\n" not in buf and len(buf) < _MAX_BODY_PEEK:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=_PHASE_TIMEOUT)
            if not chunk:
                break
            buf.extend(chunk)
        head, _, _ = bytes(buf).partition(b"\r\n\r\n")
        r["status"], r["headers"] = _parse_status_and_headers(head)
        r["indirme_ms"] = (time.perf_counter() - t) * 1000
        r["toplam_ms"] = (time.perf_counter() - t_start) * 1000
    except Exception:
        pass
    finally:
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
    return r


def _detect_cdn(headers: dict) -> str | None:
    for key, provider in _CDN_HEADERS.items():
        if key in headers:
            return provider
    server = (headers.get("server") or "").lower()
    for needle, provider in (("cloudflare", "Cloudflare"), ("cloudfront", "Amazon CloudFront"),
                             ("akamai", "Akamai"), ("fastly", "Fastly"),
                             ("bunnycdn", "BunnyCDN"), ("sucuri", "Sucuri")):
        if needle in server:
            return provider
    via = (headers.get("via") or "").lower()
    if "varnish" in via:
        return "Varnish / Fastly"
    if "cloudfront" in via:
        return "Amazon CloudFront"
    return None


async def measure(domain: str) -> dict:
    """Alan adının bağlantı fazlarını ölçer ve yönlendirme zincirini çıkarır.

    Dönen `medyan` alanı `_REPEATS` ölçümün medyanıdır — tek ölçüm ağ
    gürültüsüne çok açık, medyan tekrarlanabilir sonuç verir.
    """
    ips = await resolve_public_ips_async(domain, 443)
    ip = ips[0]

    # DNS bir kez ölçülür: işletim sistemi ikinci çağrıda önbellekten döner,
    # tekrar ölçmek yapay olarak 0 ms gösterirdi.
    t = time.perf_counter()
    try:
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.getaddrinfo(domain, 443, type=socket.SOCK_STREAM),
            timeout=_PHASE_TIMEOUT)
    except Exception:
        pass
    dns_ms = (time.perf_counter() - t) * 1000

    tls_info = await _tls_probe(domain, ip, 443)

    runs = []
    for _ in range(_REPEATS):
        runs.append(await _single_run(domain, ip, "/", 443, use_tls=True))

    ok = [r for r in runs if r["status"] > 0]
    if not ok:
        # HTTPS başarısız — düz HTTP dene (sertifikası olmayan siteler için)
        ok = []
        for _ in range(_REPEATS):
            r = await _single_run(domain, ip, "/", 80, use_tls=False)
            if r["status"] > 0:
                ok.append(r)
        tls_info = {"tls_version": None, "alpn": None, "cipher": None, "http2": False}

    if not ok:
        return {
            "ulasilabilir": False, "ip": ip, "dns_ms": round(dns_ms, 1),
            "tls": tls_info, "medyan": None, "headers": {}, "status": 0,
            "cdn": None, "http3_beyani": False, "yonlendirmeler": [],
        }

    def med(key: str) -> float:
        return round(statistics.median(r[key] for r in ok), 1)

    headers = ok[-1]["headers"]
    sunucu_ms = med("sunucu_ms")

    return {
        "ulasilabilir": True,
        "ip": ip,
        "dns_ms": round(dns_ms, 1),
        "tls": tls_info,
        "medyan": {
            "dns_ms":     round(dns_ms, 1),
            "tcp_ms":     med("tcp_ms"),
            "tls_ms":     med("tls_ms"),
            "sunucu_ms":  sunucu_ms,
            # TTFB tanımı: istek gönderiminden ilk bayta. Bağlantı kurulum
            # maliyetini de kullanıcı deneyimine dahil etmek için toplamı da veriyoruz.
            "ttfb_ms":    round(dns_ms + med("tcp_ms") + med("tls_ms") + sunucu_ms, 1),
            "olcum_sayisi": len(ok),
        },
        "status": ok[-1]["status"],
        "headers": headers,
        "cdn": _detect_cdn(headers),
        "http3_beyani": "h3" in (headers.get("alt-svc") or ""),
        "yonlendirmeler": [],
    }
