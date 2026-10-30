@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call setup.bat
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-dev.txt
".venv\Scripts\python.exe" -m pytest -q
pause
