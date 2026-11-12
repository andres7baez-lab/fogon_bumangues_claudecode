#!/bin/bash
# Inicia El Fogón Bumangués en Mac. La primera vez prepara el entorno.
cd "$(dirname "$0")" || exit 1

if [ ! -f .env ]; then
  echo "Falta el archivo .env con la URL de la base de datos."
  echo "Copie .env.example como .env y llene DATABASE_URL y SECRET_KEY. Vea el README."
  read -r -p "Presione Enter para salir"
  exit 1
fi

# Usa Python 3.12 si está instalado; si no, python3.
PY=python3
command -v python3.12 >/dev/null 2>&1 && PY=python3.12

if ! .venv/bin/python -c "import flask, psycopg, dotenv" 2>/dev/null; then
  echo "Preparando el programa por primera vez, puede tardar un par de minutos..."
  rm -rf .venv
  if ! "$PY" -m venv .venv || ! .venv/bin/python -m pip install -r requirements.txt; then
    echo ""
    echo "No se pudo preparar el programa. Revise que Python 3.12 esté instalado (vea el README)."
    read -r -p "Presione Enter para salir"
    exit 1
  fi
fi

.venv/bin/python app.py
