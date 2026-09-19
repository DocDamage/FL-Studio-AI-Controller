@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run SETUP_WINDOWS.cmd first.
  pause
  exit /b 1
)
echo Start START_LIVE.cmd before this check. No second MIDI connection will be opened.
".venv\Scripts\python.exe" -m flcopilot --diagnose
set "RESULT=%ERRORLEVEL%"
echo.
echo Exit 0: live bridge preconditions ready. Exit 2: not ready or no running app.
echo A ready check is not permission to modify FL and not full host acceptance.
pause
exit /b %RESULT%
