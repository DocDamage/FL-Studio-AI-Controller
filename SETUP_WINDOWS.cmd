@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Setup-Windows.ps1"
if errorlevel 1 echo Setup stopped with an error. Read the message above.
pause
