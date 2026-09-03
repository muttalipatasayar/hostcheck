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
# veritabanına migration uygular ve hazır yanıt testleri oraya yazardı.
_TEST_DB = os.path.join(tempfile.mkdtemp(prefix="hostcheck-test-"), "test.db")
os.environ.setdefault("HOSTCHECK_DB_URL", f"sqlite:///{_TEST_DB}")

# `setdefault`: dışarıdan verilmişse ona saygı duyulur.
os.environ.setdefault("ENV", "development")
os.environ.setdefault("CORS_ORIGINS", "http://testserver,http://localhost:5173")

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


@pytest.fixture
def istemci():
    """Lifespan çalıştıran TestClient — hazır yanıt tohumlaması açılışta olur."""
    from fastapi.testclient import TestClient
    import main

    with TestClient(main.app, base_url="http://testserver") as c:
        yield c
