@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: running setup...
  call setup.bat
)
if not exist ".env" (
  echo backend\.env is missing - run setup.bat first.
  pause
  exit /b 1
)
echo Wire API starting on http://127.0.0.1:8000  (Ctrl+C to stop)
".venv\Scripts\python.exe" run.py
pause
