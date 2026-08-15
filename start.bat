@echo off
echo HostCheck baslatiliyor...
echo.

:: Backend'i ayri pencerede baslat
:: DIKKAT: Panelde kimlik dogrulama yoktur. --host 0.0.0.0 yaparsaniz agdaki
:: herkes SSH/RDP tunellerinizi ve veritabanini kullanabilir. 127.0.0.1'de birakin.
start "HostCheck Backend" cmd /k "cd /d "%~dp0backend" && call venv\Scripts\activate.bat && uvicorn main:app --reload --host 127.0.0.1 --port 8000"

:: 2 saniye bekle (backend ayaga kalksin)
timeout /t 2 /nobreak >nul

:: Frontend'i ayri pencerede baslat
start "HostCheck Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

:: 3 saniye bekle (frontend ayaga kalksin)
timeout /t 3 /nobreak >nul

:: Tarayiciyi ac
start "" "http://localhost:5173"

echo.
echo Backend  : http://127.0.0.1:8000
echo Frontend : http://localhost:5173
echo.
echo Kapatmak icin her iki pencereyi de kapatin.
