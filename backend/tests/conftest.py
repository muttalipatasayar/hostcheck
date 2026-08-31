"""Testler backend/ kökünden import edebilsin diye yol ayarı + rate limit.

Projede paket yapısı yok (main.py, net_validation.py vb. düz modüller);
uygulama da `cd backend && uvicorn main:app` ile çalışıyor. Testler de aynı
kökü görmeli.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
