@echo off
setlocal
cd /d "%~dp0"
echo.
echo === Wire backend setup ===

set "PY="
py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3.12 was not found. Install it from https://www.python.org/downloads/ and run this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv .venv
  if errorlevel 1 ( echo Could not create .venv & pause & exit /b 1 )
)

echo Installing packages (hash-checked)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --require-hashes -r requirements.txt
if errorlevel 1 ( echo Package install failed & pause & exit /b 1 )

echo.
echo Setting up .env ...
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\make_env.ps1"
if errorlevel 1 ( echo .env setup failed & pause & exit /b 1 )

echo.
echo Setup finished. Start the server with start.bat
pause
