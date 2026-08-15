@echo off
echo HostCheck Backend baslatiliyor...
cd /d "%~dp0backend"

if not exist "venv" (
    echo Virtual environment olusturuluyor...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Bagimliliklar yukleniyor...
pip install -r requirements.txt --quiet

echo Playwright tarayicisi kontrol ediliyor...
python -m playwright install chromium --with-deps >nul 2>&1

if not exist ".env" (
    echo .env dosyasi bulunamadi. .env.example kopyalaniyor...
    copy .env.example .env
)

echo.
echo Backend http://127.0.0.1:8000 adresinde baslatiliyor...
echo API docs: http://127.0.0.1:8000/docs
echo.
:: DIKKAT: Panelde kimlik dogrulama yoktur. --host 0.0.0.0 yaparsaniz agdaki
:: herkes SSH/RDP tunellerinizi ve veritabanini kullanabilir. 127.0.0.1'de birakin.
uvicorn main:app --reload --host 127.0.0.1 --port 8000
