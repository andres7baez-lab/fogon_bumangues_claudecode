"""Conexión a la base de datos PostgreSQL (Neon) con psycopg 3.

Todo el acceso a la base pasa por aquí. Variables de entorno:

  DATABASE_URL  URL con pooler (el host contiene "-pooler"). La usa la
                aplicación web: el pooler reparte muchas conexiones cortas.
  DIRECT_URL    URL directa (sin "-pooler"). La usan manage.py y seed.py
                para crear tablas y cargar datos. Si falta, se deriva de
                DATABASE_URL quitando "-pooler" del host.

En Postgres las llaves foráneas siempre se verifican (no hace falta
ningún PRAGMA como en SQLite).
"""
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import sql

CARPETA = Path(__file__).resolve().parent
RUTA_SCHEMA = CARPETA / "schema.sql"


def cargar_env(archivo=None):
    """Lee las variables del archivo .env (solo en el computador local).

    En Vercel no hay archivo .env: las variables vienen del panel del proyecto.
    Con `archivo` se lee otro archivo (p. ej. .env.produccion) y sus valores
    reemplazan a los que ya estuvieran cargados.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    ruta = Path(archivo) if archivo else CARPETA / ".env"
    if archivo and not ruta.exists():
        raise SystemExit(f"No existe el archivo {ruta}.")
    load_dotenv(ruta, override=bool(archivo))


def sin_pooler(url):
    """Convierte la URL con pooler de Neon en la URL directa (quita '-pooler' del host)."""
    return url.replace("-pooler.", ".", 1)


def url_app():
    """URL que usa la aplicación web (con pooler)."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Falta la variable DATABASE_URL (vea .env.example).")
    return url


def url_directa():
    """URL para crear tablas y cargar datos (directa)."""
    return os.environ.get("DIRECT_URL") or sin_pooler(url_app())


def host_de(url):
    """Solo el servidor de la URL, para mostrarlo sin la contraseña."""
    return url.split("@")[-1].split("/")[0].split("?")[0]


class Fila(tuple):
    """Fila que se lee por nombre (fila["nombre"]) o por posición (fila[0]).

    Funciona igual que sqlite3.Row, así el resto del código no cambia y en
    las plantillas se puede escribir venta.estado.
    """

    def __new__(cls, valores, indice):
        fila = super().__new__(cls, valores)
        fila._indice = indice
        return fila

    def __getitem__(self, clave):
        if isinstance(clave, str):
            return tuple.__getitem__(self, self._indice[clave])
        return tuple.__getitem__(self, clave)

    def keys(self):
        return list(self._indice)

    def get(self, clave, por_defecto=None):
        return self[clave] if clave in self._indice else por_defecto


def _fabrica_de_filas(cursor):
    columnas = [c.name for c in cursor.description] if cursor.description else []
    indice = {nombre: i for i, nombre in enumerate(columnas)}
    return lambda valores: Fila(valores, indice)


def conectar(url=None, esquema=None):
    """Abre una conexión nueva.

    Se usa modo 'autocommit' y las transacciones se marcan a mano con
    transaccion(), así queda explícito qué operaciones van juntas.
    prepare_threshold=None desactiva las sentencias preparadas, que no
    se llevan bien con el pooler de Neon.
    `esquema` solo lo usan las pruebas, para trabajar en un esquema aparte.
    """
    con = psycopg.connect(url or url_app(), autocommit=True, row_factory=_fabrica_de_filas,
                          prepare_threshold=None, connect_timeout=20)
    if esquema:
        con.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(esquema)))
    return con


@contextmanager
def transaccion(con):
    """Agrupa varias instrucciones: o se guardan todas o no se guarda ninguna."""
    with con.transaction():
        yield con


def obtener_bd():
    """Conexión de la petición web actual.

    Se abre al primer uso y se cierra al terminar la petición (ver app.py):
    en Vercel cada petición puede correr en una instancia distinta.
    """
    from flask import current_app, g
    if "bd" not in g:
        g.bd = conectar(current_app.config["DATABASE_URL"], current_app.config.get("ESQUEMA_BD"))
    return g.bd


def crear_tablas(con):
    """Ejecuta schema.sql (CREATE TABLE IF NOT EXISTS: se puede repetir sin error)."""
    con.execute(RUTA_SCHEMA.read_text(encoding="utf-8"))


def tablas_creadas(con):
    """True si ya existen las tablas del sistema."""
    return con.execute("SELECT to_regclass('pago') IS NOT NULL").fetchone()[0]
