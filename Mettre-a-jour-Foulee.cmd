@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Tout sur une ligne : la mise a jour peut remplacer ce fichier pendant qu'il s'execute
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\mettre-a-jour.ps1" %* & echo. & pause & exit /b
