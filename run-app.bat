@echo off
echo ===================================================
echo Starting PDF RAG Assistant (Backend + Frontend)
echo ===================================================

echo [1/2] Starting Backend on http://127.0.0.1:8001...
start "Backend - FastAPI" powershell -NoExit -Command "cd '%~dp0backend'; .\.venv\Scripts\Activate.ps1; uvicorn app:app --reload --host 127.0.0.1 --port 8001"

echo [2/2] Starting Frontend on http://localhost:3000...
start "Frontend - Next.js" powershell -NoExit -Command "cd '%~dp0frontend'; npm run dev"

echo.
echo Both servers have been launched in separate terminal windows.
echo - Web UI:  http://localhost:3000
echo - API Docs: http://127.0.0.1:8001/docs
echo ===================================================
pause

