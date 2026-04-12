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

if not exist ".env" (
    echo .env dosyasi bulunamadi. .env.example kopyalaniyor...
    copy .env.example .env
    echo UYARI: backend\.env dosyasina ANTHROPIC_API_KEY ekleyin!
)

echo.
echo Backend http://localhost:8000 adresinde baslatiliyor...
echo API docs: http://localhost:8000/docs
echo.
uvicorn main:app --reload --host 0.0.0.0 --port 8000
