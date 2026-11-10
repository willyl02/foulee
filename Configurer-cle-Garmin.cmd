@echo off
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\foulee.exe" setup
echo.
pause
