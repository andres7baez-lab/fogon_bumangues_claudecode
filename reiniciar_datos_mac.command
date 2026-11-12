#!/bin/bash
# BORRA lo registrado en la base del archivo .env y vuelve a cargar la demo.
cd "$(dirname "$0")" || exit 1
echo "Este programa BORRA todas las ventas, cierres y cambios de la base del archivo .env"
echo "y vuelve a cargar la demo: catálogo, usuarios y cierres de los últimos 30 días."
echo ""
if [ ! -x .venv/bin/python ]; then
  echo "Ejecute primero iniciar_mac.command una vez."
  read -r -p "Presione Enter para salir"
  exit 1
fi
.venv/bin/python seed.py --reset
read -r -p "Presione Enter para salir"
