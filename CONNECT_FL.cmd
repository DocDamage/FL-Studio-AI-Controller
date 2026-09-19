@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Connect-FL.ps1"
if errorlevel 1 echo Connection setup stopped. Existing projects were not saved or modified by this launcher.
pause
