@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if errorlevel 1 goto failed
if not exist .env copy .env.example .env >nul
.venv\Scripts\python.exe -m alembic upgrade head
if errorlevel 1 goto failed
echo Open http://127.0.0.1:8000 in your browser.
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
exit /b
:failed
echo Setup failed. Install Python 3.12 and check the error above.
pause
exit /b 1
