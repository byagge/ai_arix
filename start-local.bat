@echo off
chcp 65001 >nul
title Arix Platform

echo.
echo   Arix Platform - local start
echo   ---------------------------
echo.

cd /d "%~dp0"

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo   .env created from template - add your provider keys there.
)

echo   Telegram: set TELEGRAM_BOT_TOKEN + TELEGRAM_ADMIN_ID in .env
echo   Check status: http://127.0.0.1:8000/health
echo.

findstr /C:"OPENAI_BASE_URL=http://127.0.0.1:8800/v1" .env >nul
if %errorlevel%==0 (
    echo   [1/3] local provider  http://127.0.0.1:8800
    start "arix-provider" cmd /k "cd /d %~dp0backend && python tools\local_provider.py"
    timeout /t 2 >nul
)

echo   [2/3] backend         http://127.0.0.1:8000
start "arix-backend" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning"

timeout /t 4 >nul

echo   [3/3] frontend        http://localhost:3000
start "arix-frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 8 >nul
start http://localhost:3000

echo.
echo   Ready. Close the spawned windows to stop the services.
echo.
