"""SSRF kapısı ve girdi doğrulama — panelin en kritik savunması.

`/api/` Nginx'te AUTH'SUZ ve internete açık. Bu kapılardan biri gevşerse
internetteki herkes paneli iç ağa istek attırmak için kullanabilir. Ağustos
2026 güvenlik denetiminin KRİTİK bulgusu tam olarak buydu; bu testler onun
geri gelmemesi için var.
"""
import pytest
from fastapi.testclient import TestClient

import main
from net_validation import is_public_ip
from routers.ssl_tools import _prepare_chain_domain
from fastapi import HTTPException


@pytest.fixture(scope="module")
def istemci():
    with TestClient(main.app) as c:
        yield c


# ── is_public_ip ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.1",
    "169.254.169.254",              # bulut metadata servisi
    "::1", "fe80::1", "fc00::1",
    "0.0.0.0", "224.0.0.1",
    "::ffff:127.0.0.1",             # IPv4-mapped IPv6 ile atlatma
])
def test_ozel_adresler_reddedilir(ip):
    assert is_public_ip(ip) is False


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700::1"])
def test_genel_adresler_kabul_edilir(ip):
    assert is_public_ip(ip) is True


# ── _prepare_chain_domain ────────────────────────────────────────────────────

def test_null_bayt_reddedilir():
    """Null bayt SİLİNMEMELİ, REDDEDİLMELİ.

    Silseydik 'a\\x00b.com' sessizce 'ab.com'a dönüşür ve teknisyene
    sorduğundan BAŞKA bir alan adının raporu gösterilirdi.
    """
    with pytest.raises(HTTPException) as e:
        _prepare_chain_domain("a\x00b.com")
    assert e.value.status_code == 400


@pytest.mark.parametrize("girdi,beklenen", [
    ("EXAMPLE.com", "example.com"),
    ("https://example.com/yol?x=1", "example.com"),
    ("example.com:8443", "example.com"),
    ("türkiye.gov.tr", "xn--trkiye-3ya.gov.tr"),   # IDN -> A-label
])
def test_domain_temizleme(girdi, beklenen):
    assert _prepare_chain_domain(girdi) == beklenen


@pytest.mark.parametrize("girdi", ["", "   ", "a b.com", "exam..ple.com", ".example.com",
                                   "example.com.", "a" * 300 + ".com"])
def test_gecersiz_domainler(girdi):
    with pytest.raises(HTTPException):
        _prepare_chain_domain(girdi)


# ── Uç nokta: port kapısı (ağ gerektirmez, çözümlemeden ÖNCE çalışır) ────────

@pytest.mark.parametrize("port", [22, 23, 3306, 6379, 0, 99999, -1])
def test_izinsiz_portlar_reddedilir(istemci, port):
    r = istemci.get("/api/ssl/chain-check", params={"domain": "example.com", "port": port})
    assert r.status_code == 400
    assert "port" in r.json()["detail"].lower()


@pytest.mark.parametrize("port", [25, 587, 21])
def test_starttls_portlari_ayri_mesaj_verir(istemci, port):
    """25/587/21 STARTTLS'tir, doğrudan TLS değil — ClientHello düz metin
    banner'a çarpıp bağlantı asılı kalırdı. Ayrı ve açıklayıcı mesaj."""
    r = istemci.get("/api/ssl/chain-check", params={"domain": "example.com", "port": port})
    assert r.status_code == 400
    assert "STARTTLS" in r.json()["detail"]


# ── Uç nokta: SSRF (IP literalleri — DNS gerektirmez) ────────────────────────

@pytest.mark.parametrize("hedef", ["127.0.0.1", "10.0.0.1", "192.168.1.1",
                                   "169.254.169.254", "0.0.0.0"])
def test_ozel_ip_hedefleri_reddedilir(istemci, hedef):
    r = istemci.get("/api/ssl/chain-check", params={"domain": hedef})
    assert r.status_code == 400


@pytest.mark.network
@pytest.mark.parametrize("hedef", ["localhost", "127.0.0.1.nip.io", "localtest.me"])
def test_ic_adrese_cozulen_isimler_reddedilir(istemci, hedef):
    """String doğrulaması yeterli DEĞİL: bu isimler formatı geçer ama
    127.0.0.1'e çözülür. Denetimin kritik bulgusu buydu."""
    r = istemci.get("/api/ssl/chain-check", params={"domain": hedef})
    assert r.status_code == 400


# ── AIA indirmesi: sertifikadan gelen URL = saldırgan denetimli ──────────────

def test_aia_url_kurallari():
    """Sadece http, sadece port 80, kimlik bilgisi yok."""
    import asyncio, httpx, ssl_chain_core as m

    async def dene(url):
        loop = asyncio.get_event_loop()
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as c:
            return await m._fetch_aia_once(c, url, loop.time() + 3, loop.time)

    for url in ["https://example.com/ca.crt",
                "http://user:pass@example.com/ca.crt",
                "http://example.com:8080/ca.crt",
                "ftp://example.com/ca.crt"]:
        certs, bulgu = asyncio.run(dene(url))
        assert certs == [], f"{url} indirilmemeliydi"
        assert bulgu is not None


# ── Rate limit ───────────────────────────────────────────────────────────────

def test_rate_limit_calisiyor(istemci):
    """Sınırın kendisi. conftest tüm testlerde limiter'ı kapatıyor; burada
    bilerek açıp gerçekten 429 döndüğünü doğruluyoruz.

    Uç auth'suz ve internete açık: sınır kalkarsa panel dışarıdan ücretsiz
    bir tarama aracına dönüşür.
    """
    from rate_limiter import limiter
    limiter.enabled = True
    try:
        kodlar = [
            istemci.get("/api/ssl/chain-check",
                        params={"domain": "example.com", "port": 22}).status_code
            for _ in range(14)
        ]
    finally:
        limiter.enabled = False
    assert 429 in kodlar, "10/dakika sınırı tetiklenmedi"
    assert kodlar.count(400) >= 8, "sınırdan önceki istekler normal işlenmeli"


# ── DoS: bloklayan iş event loop'ta olmamalı ─────────────────────────────────

def test_aia_cozumlemesi_event_loopu_bloklamaz(monkeypatch):
    """AIA hostunun NAMESERVER'I SALDIRGANIN.

    Sertifikanın AIA alanını hedef alan adının sahibi belirler; dolayısıyla o
    hostun nameserver'ını da o kontrol eder. Yanıt vermeyen bir nameserver ile
    TEK bir istek, tek worker'lı panelin event loop'unu işletim sisteminin
    resolver zaman aşımı boyunca dondurabiliyordu — auth'suz bir uçtan tam
    servis kesintisi. Çözümleme executor'a alındı.
    """
    import asyncio
    import socket
    import time

    import net_validation
    import ssl_chain_core as m

    def yavas_cozumleme(*a, **k):
        time.sleep(2.0)
        raise socket.gaierror("timeout")

    monkeypatch.setattr(net_validation.socket, "getaddrinfo", yavas_cozumleme)

    async def kalp_atisi(bayrak):
        en_uzun, son = 0.0, time.monotonic()
        while not bayrak.is_set():
            await asyncio.sleep(0.05)
            simdi = time.monotonic()
            en_uzun = max(en_uzun, simdi - son)
            son = simdi
        return en_uzun

    async def senaryo():
        bayrak = asyncio.Event()
        kalp = asyncio.create_task(kalp_atisi(bayrak))
        await asyncio.sleep(0.2)
        sonuc = await m._resolve_public_or_none("saldirgan-nameserver.example")
        bayrak.set()
        return sonuc, await kalp

    sonuc, en_uzun_donma = asyncio.run(senaryo())
    assert sonuc is None, "çözümlenemeyen host reddedilmeli"
    assert en_uzun_donma < 0.5, (
        f"event loop {en_uzun_donma:.2f} sn dondu — bloklayan çağrı geri gelmiş"
    )


def test_tls_isleri_paylasilan_havuzda_degil():
    """El sıkışmalar AYRILMIŞ havuzda olmalı.

    Varsayılan havuzu resolve_public_ips_async, whois ve dnspython paylaşıyor.
    10 sn'ye kadar thread tutan bir el sıkışma oraya girerse, havuz dolduğunda
    ALÂKASIZ araçlar zaman aşımına düşer.
    """
    import ssl_chain_core
    from routers import ssl_tools

    assert ssl_tools._CHAIN_EXECUTOR is ssl_chain_core.CHAIN_EXECUTOR
    assert ssl_chain_core.CHAIN_EXECUTOR._max_workers == 2

    # quick_check teşhisi de aynı havuzu kullanmalı
    kaynak = open("routers/quick_check.py", encoding="utf-8").read()
    assert "ssl_chain_core.CHAIN_EXECUTOR, _ssl_failure_reason" in kaynak, \
        "do_ssl teşhisi hâlâ varsayılan havuzda"


def test_aia_url_crlf_enjeksiyonu():
    """AIA URL'i sertifikadan gelir; CRLF ile başlık enjekte edilememeli."""
    import urllib.parse

    for kotu in ["http://evil.com\r\nX-Injected: 1/ca.crt",
                 "http://evil.com/ca.crt\r\nX-Injected: 1",
                 "http://evil.com/ca.crt?x=1\r\nHost: internal"]:
        p = urllib.parse.urlsplit(kotu)
        host = p.hostname or ""
        yol = (p.path or "/") + (("?" + p.query) if p.query else "")
        assert "\r" not in host + yol and "\n" not in host + yol
