@echo off
REM ─────────────────────────────────────────────────
REM FBT Mock — Start both backend and frontend
REM Usage:  start.bat
REM ─────────────────────────────────────────────────

title FBT Mock — AI Interview Simulator
echo.
echo   FBT Mock — AI Interview Simulator
echo   ─────────────────────────────────────
echo.

REM ── Check prerequisites ──
where python >nul 2>&1 || (echo [ERROR] Python not found. Install from https://python.org && pause && exit /b 1)
where node >nul 2>&1 || (echo [ERROR] Node.js not found. Install from https://nodejs.org && pause && exit /b 1)
where npm >nul 2>&1 || (echo [ERROR] npm not found. && pause && exit /b 1)

echo [OK] Python found
echo [OK] Node.js found
echo.

REM ── Install backend deps ──
echo Installing backend dependencies...
cd /d "%~dp0backend"
python -m pip install -r requirements.txt || (echo [ERROR] Backend dependency install failed && pause && exit /b 1)
echo [OK] Backend dependencies ready

REM ── Install frontend deps ──
echo Installing frontend dependencies...
cd /d "%~dp0"
if exist "package-lock.json" (
    npm ci || (echo [ERROR] Frontend dependency install failed && pause && exit /b 1)
) else (
    npm install || (echo [ERROR] Frontend dependency install failed && pause && exit /b 1)
)
echo [OK] Frontend dependencies ready
echo.

REM ── Start backend in new window ──
echo Starting backend on port 8000...
cd /d "%~dp0backend"
start "FBT Mock Backend" cmd /c "python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 2 /nobreak >nul

REM ── Start frontend in new window ──
echo Starting frontend on port 5173...
cd /d "%~dp0"
start "FBT Mock Frontend" cmd /c "npx vite --port 5173"
timeout /t 2 /nobreak >nul

echo.
echo   ─────────────────────────────────────
echo   Ready! Open http://localhost:5173
echo   Click the gear icon to configure your LLM provider
echo   ─────────────────────────────────────
echo.
echo   Close this window or press Ctrl+C to stop.
echo.
pause
