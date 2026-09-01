"""Site Hızı ölçüm deposunun kaynak sınırları.

`/api/site-speed/run` kimlik doğrulaması istemiyor. Depo katmanının tek
başına tutması gereken sınır, o ucun kötüye kullanılmasıyla diskin
doldurulmamasıdır.
"""
import pytest

from database import SessionLocal
from models import SiteHiziOlcum
from routers.site_speed import store as st


@pytest.fixture
def db():
    import main  # noqa: F401 — şemayı Alembic ile kurar
    oturum = SessionLocal()
    oturum.query(SiteHiziOlcum).delete()
    oturum.commit()
    try:
        yield oturum
    finally:
        oturum.query(SiteHiziOlcum).delete()
        oturum.commit()
        oturum.close()


def _kaydet(db, domain, strateji="mobile"):
    st.kaydet(db, domain, strateji, {"skor": 50, "metrikler": {}})


def test_grup_ici_budama(db, monkeypatch):
    """Aynı alan adı + strateji için son N kayıt tutulur."""
    monkeypatch.setattr(st, "_MAX_KAYIT", 5)
    for _ in range(12):
        _kaydet(db, "ayni.example")
    assert db.query(SiteHiziOlcum).count() <= 6


def test_farkli_alan_adlari_toplam_tavani_asamaz(db, monkeypatch):
    """ASIL AÇIK: grup içi budama farklı alan adlarıyla ATLANIYORDU.

    Saldırgan her istekte farklı bir alan adı verirse her kayıt kendi
    grubunda tek başına kalır ve grup içi eşiği hiç aşmaz. 5/dakika sınırıyla
    bile yılda ~2,6 milyon satır demekti — SQLite dosyası sınırsız büyür.
    """
    monkeypatch.setattr(st, "_MAX_TOPLAM_KAYIT", 20)
    for i in range(60):
        _kaydet(db, f"site{i}.example")
    toplam = db.query(SiteHiziOlcum).count()
    assert toplam <= 21, f"toplam tavan tutmadı: {toplam} satır"


def test_budama_en_yenileri_korur(db, monkeypatch):
    """Tavan aşılınca EN ESKİ kayıtlar silinmeli; yeni ölçüm hep saklanmalı."""
    monkeypatch.setattr(st, "_MAX_TOPLAM_KAYIT", 5)
    for i in range(15):
        _kaydet(db, f"s{i:02d}.example")
    kalan = {r.domain for r in db.query(SiteHiziOlcum).all()}
    assert "s14.example" in kalan, "en son ölçüm silinmiş"
    assert "s00.example" not in kalan, "en eski kayıt hâlâ duruyor"
