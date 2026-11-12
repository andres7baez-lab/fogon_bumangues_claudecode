@echo off
chcp 65001 > nul
title Reiniciar datos - El Fogon Bumangues
cd /d "%~dp0"
echo Este programa BORRA todas las ventas, cierres y cambios de la base del archivo .env
echo y vuelve a cargar la demo: catalogo, usuarios y cierres de los ultimos 30 dias.
echo.
if not exist ".venv\Scripts\python.exe" (
  echo Ejecute primero iniciar_windows.bat una vez.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" seed.py --reset
pause
