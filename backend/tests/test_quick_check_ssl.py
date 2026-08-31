"""Hızlı Kontrol'ün SSL satırı doğru sebebi söylüyor mu?

Eskiden `except Exception` her şeyi "HTTPS yok — sitenin HTTPS'i olmayabilir"
diye raporluyordu. Sahadaki en yaygın vaka (sunucu ara sertifikayı
göndermiyor) tam oraya düşüyordu: site HTTPS konuşuyor, sertifika geçerli,
ama Python'ın ssl modülü Android gibi AIA çekmediği için doğrulayamıyor.
Teknisyene "HTTPS yok" demek onu yanlış yere bakmaya gönderiyordu.

Testler ağsız: fetch_chain_sync monkeypatch'lenip sentetik zincir veriliyor.
"""
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

import ssl_chain_core
from routers.quick_check import _ssl_failure_reason

UTC = datetime.timezone.utc


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _cert(konu, veren, veren_key, key, ca=False, gun=200, gecmis=1, sanlar=None):
    nb = datetime.datetime.now(UTC) - datetime.timedelta(days=gecmis)
    b = (x509.CertificateBuilder()
         .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, konu)]))
         .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, veren)]))
         .public_key(key.public_key())
         .serial_number(x509.random_serial_number())
         .not_valid_before(nb)
         .not_valid_after(nb + datetime.timedelta(days=gun))
         .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if not ca:
        adlar = sanlar if sanlar is not None else [konu]
        if adlar:
            b = b.add_extension(
                x509.SubjectAlternativeName([x509.DNSName(a) for a in adlar]), critical=False)
        b = b.add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
    return b.sign(veren_key, hashes.SHA256())


@pytest.fixture
def sahte_zincir(monkeypatch):
    """fetch_chain_sync'i verilen sertifika listesiyle değiştirir."""
    def kur(certs):
        def sahte(domain, ip, port, use_sni=True):
            return ssl_chain_core.HandshakeResult(certs=list(certs), protocol="TLSv1.3")
        monkeypatch.setattr(ssl_chain_core, "fetch_chain_sync", sahte)
    return kur


def test_eksik_ara_sertifika_android_uyarisi_verir(sahte_zincir):
    """EN ÖNEMLİ TEST: eski kod buna 'HTTPS yok' diyordu."""
    kok_k, ara_k, yap_k = _key(), _key(), _key()
    _cert("Kok", "Kok", kok_k, kok_k, ca=True, gun=3650)
    ara = _cert("Ara", "Kok", kok_k, ara_k, ca=True, gun=1800)
    yaprak = _cert("site.example", "Ara", ara_k, yap_k)

    sahte_zincir([yaprak])                     # sunucu YALNIZCA yaprağı gönderiyor
    value, detail = _ssl_failure_reason("site.example", "1.2.3.4")

    assert value == "Zincir eksik"
    assert "Android" in detail
    assert "HTTPS" not in value


def test_suresi_dolmus(sahte_zincir):
    k = _key()
    yaprak = _cert("site.example", "site.example", k, k, gun=10, gecmis=400)
    sahte_zincir([yaprak])
    value, detail = _ssl_failure_reason("site.example", "1.2.3.4")
    assert value == "Süresi dolmuş" and "dolmuş" in detail


def test_alan_adi_eslesmiyor(sahte_zincir):
    k = _key()
    yaprak = _cert("baska.example", "baska.example", k, k, sanlar=["baska.example"])
    sahte_zincir([yaprak])
    value, detail = _ssl_failure_reason("site.example", "1.2.3.4")
    assert value == "Alan adı eşleşmiyor" and "baska.example" in detail


def test_san_yok(sahte_zincir):
    k = _key()
    yaprak = _cert("site.example", "site.example", k, k, sanlar=[])
    sahte_zincir([yaprak])
    value, _ = _ssl_failure_reason("site.example", "1.2.3.4")
    assert value == "SAN alanı yok"


def test_kendinden_imzali(sahte_zincir):
    k = _key()
    yaprak = _cert("site.example", "site.example", k, k)
    sahte_zincir([yaprak])
    value, _ = _ssl_failure_reason("site.example", "1.2.3.4")
    assert value == "Kendinden imzalı"


def test_guvenilmeyen_kok(sahte_zincir):
    kok_k, yap_k = _key(), _key()
    kok = _cert("Sahte Kok", "Sahte Kok", kok_k, kok_k, ca=True, gun=3650)
    yaprak = _cert("site.example", "Sahte Kok", kok_k, yap_k)
    sahte_zincir([yaprak, kok])
    value, detail = _ssl_failure_reason("site.example", "1.2.3.4")
    assert value == "Kök güvenilmiyor" and "Sahte Kok" in detail


def test_yanlis_bundle(sahte_zincir):
    """chain[1] yaprağı gerçekten imzalamamışsa — başka sitenin bundle'ı."""
    kok_k, ara_k, yap_k, sahte_k = _key(), _key(), _key(), _key()
    _cert("Kok", "Kok", kok_k, kok_k, ca=True, gun=3650)
    ara = _cert("Ara", "Kok", kok_k, ara_k, ca=True, gun=1800)
    yaprak = _cert("site.example", "Ara", ara_k, yap_k)
    sahte_ara = _cert("Ara", "Kok", sahte_k, sahte_k, ca=True, gun=1800)  # aynı ad, farklı anahtar
    sahte_zincir([yaprak, sahte_ara])
    value, _ = _ssl_failure_reason("site.example", "1.2.3.4")
    assert value == "Zincir hatalı"


def test_sertifika_yok(sahte_zincir):
    sahte_zincir([])
    value, _ = _ssl_failure_reason("site.example", "1.2.3.4")
    assert value == "Sertifika alınamadı"
