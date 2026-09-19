@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto done
".venv\Scripts\python.exe" -m pytest -q tests
:done
pause
