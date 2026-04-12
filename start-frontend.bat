@echo off
echo HostCheck Frontend baslatiliyor...
cd /d "%~dp0frontend"

if not exist "node_modules" (
    echo npm bagimliliklar yukleniyor...
    npm install
)

echo.
echo Frontend http://localhost:5173 adresinde baslatiliyor...
echo.
npm run dev
