@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Foulee demo (serveur local)
".venv\Scripts\foulee.exe" web --demo --port 8771
if errorlevel 1 pause
