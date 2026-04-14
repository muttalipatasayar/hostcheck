@echo off
echo HostCheck baslatiliyor...
echo.

:: Backend'i ayrı pencerede başlat
start "HostCheck Backend" cmd /k "cd /d "%~dp0backend" && call venv\Scripts\activate.bat && uvicorn main:app --reload --host 0.0.0.0 --port 8000"

:: 2 saniye bekle (backend ayağa kalksın)
timeout /t 2 /nobreak >nul

:: Frontend'i ayrı pencerede başlat
start "HostCheck Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

:: 3 saniye bekle (frontend ayağa kalksın)
timeout /t 3 /nobreak >nul

:: Tarayıcıyı aç
start "" "http://localhost:5173"

echo.
echo Backend  : http://localhost:8000
echo Frontend : http://localhost:5173
echo.
echo Kapatmak icin her iki pencereyi de kapatin.
