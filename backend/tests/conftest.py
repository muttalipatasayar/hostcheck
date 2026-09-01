"""Testler backend/ kökünden import edebilsin diye yol ayarı + rate limit.

Projede paket yapısı yok (main.py, net_validation.py vb. düz modüller);
uygulama da `cd backend && uvicorn main:app` ile çalışıyor. Testler de aynı
kökü görmeli.
"""
import os
import sys
import tempfile

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

# ── Veritabanı izolasyonu — `database` HERHANGİ bir modülden import edilmeden
# ÖNCE ayarlanmalı; `database.py` URL'i modül seviyesinde okuyor.
#
# `SQLALCHEMY_DATABASE_URL` göreli (`sqlite:///./hostcheck.db`) ve pytest
# backend/ kökünden çalışıyor: bu kanca olmadan test koşusu GELİŞTİRME
# veritabanına migration uygular ve üyelik testleri oraya kullanıcı, oturum,
# denetim satırları yazardı.
_TEST_DB = os.path.join(tempfile.mkdtemp(prefix="hostcheck-test-"), "test.db")
os.environ.setdefault("HOSTCHECK_DB_URL", f"sqlite:///{_TEST_DB}")

# Üyelik testlerinin dayandığı ortam. `setdefault`: dışarıdan verilmişse
# ona saygı duyulur.
os.environ.setdefault("ENV", "development")          # SMTP yok → mail dosyaya
os.environ.setdefault("IZINLI_MAIL_ALANLARI", "natro.com,team.blue")
os.environ.setdefault("ADMIN_EPOSTALARI", "yonetici@sirketiniz.com")
os.environ.setdefault("CORS_ORIGINS", "http://testserver,http://localhost:5173")

# Geliştirme modunda mailler dosyaya yazılıyor; kaynak ağacı kirlenmesin.
_MAIL_DIZINI = os.path.join(os.path.dirname(_TEST_DB), "mail-out")
os.environ.setdefault("MAIL_CIKTI_DIZINI", _MAIL_DIZINI)

import pytest  # noqa: E402
from rate_limiter import limiter  # noqa: E402


@pytest.fixture(autouse=True)
def _rate_limiti_kapat():
    """Rate limit testlerde KAPALI.

    Uçların çoğu 10-20/dakika ile sınırlı; onlarca doğrulama testi aynı
    istemciden geldiği için sınır tetikleniyor ve testler 400 yerine 429
    görüyordu — yani gerçek bir hatayı değil, test kurgusunu ölçüyorduk.

    Sınırın KENDİSİ test_rate_limit_calisiyor içinde ayrıca doğrulanıyor.
    """
    limiter.enabled = False
    yield
    limiter.enabled = True


# ── Üyelik test yardımcıları ─────────────────────────────────────────────────

import email  # noqa: E402
import email.policy  # noqa: E402
import glob  # noqa: E402
import re  # noqa: E402


@pytest.fixture(autouse=True)
def _uyelik_tablolarini_temizle():
    """Her test kendi boş üyelik durumuyla başlasın.

    Tek bir dosya veritabanını paylaşan testler birbirinin kullanıcısını
    görüyordu: bir testte parola değiştiren başka bir test, sonraki testin
    giriş adımını kırıyordu. Hazır yanıt tabloları KORUNUR — tohumlama
    yalnızca lifespan'da bir kez çalışıyor.
    """
    # `import main` şemayı Alembic ile kurar; fixture ilk testte tablolar
    # henüz yokken çalışırsa "no such table" alırdı.
    import main  # noqa: F401
    from database import SessionLocal
    from models import DenetimKaydi, EpostaTokeni, Kullanici, Oturum

    db = SessionLocal()
    try:
        for model in (Oturum, EpostaTokeni, DenetimKaydi, Kullanici):
            db.query(model).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def istemci():
    """Lifespan çalıştıran TestClient — hazır yanıt tohumlaması açılışta olur."""
    from fastapi.testclient import TestClient
    import main

    with TestClient(main.app, base_url="http://testserver") as c:
        yield c


def son_mail_metni() -> str:
    """En son yazılan .eml'nin düz metin gövdesi (quoted-printable çözülmüş)."""
    dosyalar = sorted(glob.glob(os.path.join(_MAIL_DIZINI, "*.eml")))
    if not dosyalar:
        return ""
    with open(dosyalar[-1], "rb") as f:
        msg = email.message_from_bytes(f.read(), policy=email.policy.default)
    govde = msg.get_body(preferencelist=("plain",))
    return govde.get_content() if govde else ""


def son_token(amac: str = "dogrula") -> str:
    """Son mailden doğrulama (`dogrula`) ya da sıfırlama (`sifre-sifirla`) tokeni."""
    desen = (r"dogrula\?token=([A-Za-z0-9_\-]+)" if amac == "dogrula"
             else r"sifre-sifirla=([A-Za-z0-9_\-]+)")
    m = re.search(desen, son_mail_metni())
    return m.group(1) if m else ""


def uye_olustur(istemci, eposta: str, parola: str = "Guclu-Parola-2026",
                ad: str = "Test Kullanici", dogrula: bool = True) -> None:
    """Kayıt + (istenirse) e-posta doğrulaması."""
    r = istemci.post("/api/uyelik/kayit",
                     json={"ad_soyad": ad, "email": eposta, "parola": parola})
    assert r.status_code == 202, r.text
    if dogrula:
        istemci.get(f"/api/uyelik/dogrula?token={son_token()}", follow_redirects=False)


def giris_yap(istemci, eposta: str, parola: str = "Guclu-Parola-2026") -> dict:
    """Giriş yapar ve durum değiştiren istekler için CSRF başlığını döndürür."""
    r = istemci.post("/api/uyelik/giris", json={"email": eposta, "parola": parola})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": istemci.cookies.get("hc_csrf")}
