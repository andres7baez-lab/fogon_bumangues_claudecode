"""Comandos de administración de la base de datos.

    python manage.py init-db                       crea las tablas (si no existen)
    python manage.py init-db --env .env.produccion usa las URLs de otro archivo

Usa DIRECT_URL (conexión directa de Neon). Se puede correr varias veces sin
error: schema.sql solo usa CREATE TABLE IF NOT EXISTS.
"""
import argparse

from db import cargar_env, conectar, crear_tablas, host_de, url_directa


def init_db(env=None):
    cargar_env()
    if env:
        cargar_env(env)
    url = url_directa()
    con = conectar(url)
    try:
        crear_tablas(con)
        tablas = [f[0] for f in con.execute(
            """SELECT table_name FROM information_schema.tables
               WHERE table_schema = current_schema() ORDER BY table_name""")]
    finally:
        con.close()
    print(f"Tablas listas en {host_de(url)}: {', '.join(tablas)}")


def main():
    p = argparse.ArgumentParser(description="Administración de la base de El Fogón Bumangués.")
    sub = p.add_subparsers(dest="comando", required=True)
    init = sub.add_parser("init-db", help="crea las tablas de schema.sql")
    init.add_argument("--env", help="archivo de variables a usar (p. ej. .env.produccion)")
    a = p.parse_args()
    if a.comando == "init-db":
        init_db(a.env)


if __name__ == "__main__":
    main()
