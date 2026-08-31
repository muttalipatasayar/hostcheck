"""Zincir doğrulama motorunun sessizce bozulabilecek parçaları.

Buradaki testlerin ortak özelliği: hepsi AĞSIZ ve deterministik. Ağ gerektiren
uçtan uca senaryolar (badssl.com paketi) elle çalıştırılıyor; burada yalnızca
yanlış cevap üretse kimsenin fark etmeyeceği saf mantık var.
"""
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

import ssl_chain_core as m


# ── Hostname eşleşmesi ────────────────────────────────────────────────────────
# Joker kuralı yanlış olursa araç "alan adı eşleşmiyor" derken eşleşiyordur ya
# da tersi — ikisi de teknisyeni yanlış yere gönderir.

@pytest.mark.parametrize("kalip,host,beklenen", [
    ("example.com",     "example.com",       True),
    ("example.com",     "www.example.com",   False),
    ("*.example.com",   "www.example.com",   True),
    ("*.example.com",   "example.com",       False),   # joker apex'i KAPSAMAZ
    ("*.example.com",   "a.b.example.com",   False),   # yalnızca TEK etiket
    ("*.com",           "example.com",       False),   # TLD jokeri kabul edilmez
    ("*",               "example.com",       False),
    ("EXAMPLE.com",     "example.COM",       True),    # büyük/küçük harf
    ("example.com.",    "example.com",       True),    # sondaki nokta
    ("",                "example.com",       False),
    ("example.com",     "",                  False),
])
def test_host_matches(kalip, host, beklenen):
    assert m._host_matches(kalip, host) is beklenen


# ── Geçerlilik süresi takvimi (CA/B Forum SC-081v3) ───────────────────────────
# Sabit 398 yazmak, Apple ve Chrome'un bugün reddettiği sertifikaları sessizce
# geçirirdi. Sınır sertifikanın notBefore'una göre belirlenir.

@pytest.mark.parametrize("tarih,limit", [
    ("2019-06-01", 825),
    ("2020-09-01", 398),
    ("2026-03-14", 398),
    ("2026-03-15", 200),   # yürürlükteki sınır
    ("2027-03-14", 200),
    ("2027-03-15", 100),
    ("2029-03-14", 100),
    ("2029-03-15", 47),
])
def test_validity_limit_days(tarih, limit):
    nb = datetime.datetime.fromisoformat(tarih).replace(tzinfo=datetime.timezone.utc)
    assert m._validity_limit_days(nb) == limit


# ── Güven depoları ────────────────────────────────────────────────────────────

def test_stores_load():
    """Altı deponun da yüklenmesi ve meta.json ile tutarlı olması."""
    meta = m.load_store_meta()
    assert meta.get("counts"), "meta.json boş — build_trust_stores.py çalıştırılmalı"
    for ad in m.STORE_NAMES:
        girdi = m.get_store(ad)
        assert girdi is not None, f"{ad} deposu yüklenemedi"
        _, certs, bozuk = girdi
        assert len(certs) == meta["counts"][ad], f"{ad}: sayı meta.json ile uyuşmuyor"
        assert bozuk == 0, f"{ad}: {bozuk} sertifika ayrıştırılamadı"


def test_stores_differ():
    """Depolar birbirinden AYRIŞMALI.

    Ayrışmasalardı platform matrisi anlamsız olurdu ve "certifi'ye bak"
    kestirmesi yeterdi. Bu test o varsayımı koruyor.
    """
    fp = lambda ad: {c.fingerprint(hashes.SHA256()) for c in m.get_store(ad)[1]}
    assert len(fp("apple") - fp("mozilla")) > 0
    assert len(fp("android") - fp("mozilla")) > 0
    assert len(fp("android") ^ fp("android7")) > 0


def test_parse_pem_blocks_bozuk_sertifikayi_atlar():
    """Tek bozuk sertifika koca depoyu düşürmemeli."""
    iyi = m.get_store("mozilla")[1][0].public_bytes(serialization.Encoding.PEM)
    bozuk = b"-----BEGIN CERTIFICATE-----\nZ0RTU0hMQU==\n-----END CERTIFICATE-----\n"
    certs, hata = m._parse_pem_blocks(iyi + bozuk + iyi)
    assert len(certs) == 2 and hata == 1


# ── AIA yükü ayrıştırma merdiveni ─────────────────────────────────────────────

def test_parse_aia_payload_der_ve_pem():
    """Birçok CA caIssuers'ı PKCS#7 sunar; yalnız DER denenirse onarım
    sessizce başarısız olur ve kullanıcıya yanlışlıkla 'onarılamıyor' denir."""
    cert = m.get_store("mozilla")[1][0]
    assert len(m._parse_aia_payload(cert.public_bytes(serialization.Encoding.DER))) == 1
    assert len(m._parse_aia_payload(cert.public_bytes(serialization.Encoding.PEM))) == 1
    assert m._parse_aia_payload(b"bu sertifika degil") == []


# ── Kendi yol kurucumuz ───────────────────────────────────────────────────────

def _cert(konu, veren_adi, veren_key, key, ca=False, gun=200, baslangic=None):
    nb = baslangic or datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    b = (x509.CertificateBuilder()
         .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, konu)]))
         .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, veren_adi)]))
         .public_key(key.public_key())
         .serial_number(x509.random_serial_number())
         .not_valid_before(nb)
         .not_valid_after(nb + datetime.timedelta(days=gun))
         .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if not ca:
        b = b.add_extension(x509.SubjectAlternativeName([x509.DNSName(konu)]), critical=False)
        b = b.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
    return b.sign(veren_key, hashes.SHA256())


@pytest.fixture(scope="module")
def zincir():
    kok_k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ara_k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    yap_k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    kok = _cert("Test Kok", "Test Kok", kok_k, kok_k, ca=True, gun=3650)
    ara = _cert("Test Ara", "Test Kok", kok_k, ara_k, ca=True, gun=1800)
    yaprak = _cert("test.local", "Test Ara", ara_k, yap_k)
    return yaprak, ara, kok


def test_build_own_path_eksik_halka(zincir):
    """Ara sertifika gönderilmezse 'eksik_halka' — Android'i kıran vaka."""
    yaprak, _, _ = zincir
    yol, sonuc = m.build_own_path(yaprak, [yaprak])
    assert sonuc == "eksik_halka" and len(yol) == 1


def test_build_own_path_kendinden_imzali_koke_ulasir(zincir):
    """Zincir tam gönderilirse kendinden imzalı köke kadar kurulmalı."""
    yaprak, ara, kok = zincir
    yol, sonuc = m.build_own_path(yaprak, [yaprak, ara, kok])
    assert sonuc == "kendinden_imzali"
    assert [m._short_name(c) for c in yol] == ["test.local", "Test Ara", "Test Kok"]


def test_build_own_path_imza_dogrulamasi_gercek(zincir):
    """Doğru KONU adına sahip ama İMZALAMAMIŞ bir sertifika kabul edilmemeli.

    Yalnızca isim eşleştirseydik, saldırgan aynı adı taşıyan sahte bir ara
    sertifikayla zinciri 'geçerli' gösterebilirdi.
    """
    yaprak, _, _ = zincir
    sahte_k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sahte_ara = _cert("Test Ara", "Test Kok", sahte_k, sahte_k, ca=True, gun=1800)
    yol, sonuc = m.build_own_path(yaprak, [yaprak, sahte_ara])
    assert sonuc == "imza_dogrulanamadi"


# ── Sertifika alan çıkarımı ───────────────────────────────────────────────────

def test_cert_info_utc_alanlari(zincir):
    """not_valid_*_utc kullanılmalı — eski alanlar kaldırılınca kırılmasın."""
    yaprak, _, _ = zincir
    now = datetime.datetime.now(datetime.timezone.utc)
    bilgi = m.cert_info(yaprak, 0, "yaprak", "sunucu", now)
    assert bilgi.common_name == "test.local"
    assert bilgi.key_algorithm == "RSA" and bilgi.key_size == 2048
    assert bilgi.signature_algorithm == "SHA256"
    assert not bilgi.expired and not bilgi.self_signed
    assert "serverAuth" in bilgi.ext_key_usage


def test_store_stale_uyarisi(monkeypatch):
    """Depolar bayatlarsa GÖRÜNÜR bir uyarı çıkmalı, sessiz kalmamalı."""
    monkeypatch.setattr(m, "_meta_cache",
                        {"generated_at": "2020-01-01T00:00:00+00:00", "counts": {}})
    etiketler = [f.label for f in m.store_health_findings()]
    assert "Kök depoları bayatlamış" in etiketler
