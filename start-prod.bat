@echo off
chcp 65001 >nul
title Arix Platform (production)

cd /d "%~dp0"

if not exist ".env" (
    echo ERROR: .env missing. Copy .env.example and fill keys.
    exit /b 1
)

echo.
echo   Arix production
echo   ---------------
echo   Logs: data\logs\arix.log
echo   Health: http://127.0.0.1:8000/health
echo   Panel:  http://127.0.0.1:3000
echo.

echo   [1/2] backend
start "arix-backend" cmd /k "cd /d %~dp0backend && set DEBUG=false && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info --workers 1"

timeout /t 4 >nul

echo   [2/2] frontend (next start - build first if needed)
if not exist "frontend\.next\BUILD_ID" (
    echo   Building frontend...
    pushd frontend
    call npm run build
    popd
)

start "arix-frontend" cmd /k "cd /d %~dp0frontend && set NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 && npm run start -- -H 0.0.0.0 -p 3000"

echo.
echo   Ready. Install as app: Chrome/Edge menu - Install Arix / Add to Home screen
echo.
