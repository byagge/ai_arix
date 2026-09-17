@echo off
echo Starting AI Sales Agent Stack...
echo.
echo 1. Copy .env.example to .env and fill in API keys
echo 2. Run: docker compose up -d
echo.
echo Services:
echo   Admin Panel:  http://localhost:3000
echo   Backend API:  http://localhost:8000
echo   API Docs:     http://localhost:8000/docs
echo.
docker compose up -d
pause
