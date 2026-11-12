"""Base de datos para las pruebas automáticas.

Las pruebas usan la base indicada en TEST_DATABASE_URL (la rama "desarrollo"
de Neon, nunca la de producción) y trabajan en un esquema aparte llamado
"pruebas": antes de cada prueba se borra y se crea de nuevo, así que no tocan
las tablas normales de esa base.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import cargar_env, conectar, crear_tablas, sin_pooler  # noqa: E402
from seed import cargar_datos_base, cargar_demo  # noqa: E402

ESQUEMA = "pruebas"

cargar_env()
_URL = os.environ.get("TEST_DATABASE_URL")
if not _URL:
    raise unittest.SkipTest("Falta TEST_DATABASE_URL en .env (URL de la rama de desarrollo de Neon).")
# Conexión directa: el cambio de esquema (SET search_path) no se conserva a través del pooler.
URL_PRUEBAS = sin_pooler(_URL)


def conectar_prueba():
    return conectar(URL_PRUEBAS, ESQUEMA)


def preparar_base(dias_demo=0):
    """Esquema "pruebas" vacío con las tablas y los datos base (y demo si se pide)."""
    con = conectar(URL_PRUEBAS)
    try:
        con.execute(f"DROP SCHEMA IF EXISTS {ESQUEMA} CASCADE")
        con.execute(f"CREATE SCHEMA {ESQUEMA}")
    finally:
        con.close()
    con = conectar_prueba()
    crear_tablas(con)
    cargar_datos_base(con)
    if dias_demo:
        cargar_demo(con, dias=dias_demo)
    return con
