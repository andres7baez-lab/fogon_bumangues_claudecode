@echo off
chcp 65001 > nul
title El Fogon Bumangues
cd /d "%~dp0"

rem Necesita el archivo .env con la URL de la base (vea el README, seccion 3).
if not exist ".env" (
  echo Falta el archivo .env con la URL de la base de datos.
  echo Copie .env.example como .env y llene DATABASE_URL y SECRET_KEY. Vea el README.
  pause
  exit /b 1
)

rem Busca Python 3.12: primero "py -3.12" (instalador de python.org) y si no, "python".
set PY=python
py -3.12 --version > nul 2> nul
if not errorlevel 1 set PY=py -3.12

rem Si el entorno no existe o le faltan librerias, se prepara (solo la primera vez).
".venv\Scripts\python.exe" -c "import flask, psycopg, dotenv" > nul 2> nul
if errorlevel 1 goto preparar
goto iniciar

:preparar
echo Preparando el programa por primera vez, puede tardar un par de minutos...
if exist ".venv" rmdir /s /q ".venv"
%PY% -m venv .venv
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error

:iniciar
".venv\Scripts\python.exe" app.py
pause
exit /b 0

:error
echo.
echo No se pudo preparar el programa.
echo Revise que Python 3.12 este instalado y que haya internet. Vea el README.
pause
exit /b 1
