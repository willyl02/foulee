@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Foulee (serveur local, garde cette fenetre ouverte)
".venv\Scripts\foulee.exe" web
if errorlevel 1 pause
