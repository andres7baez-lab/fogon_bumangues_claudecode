"""Aplicación web de El Fogón Bumangués.

En el computador:  python app.py   y abrir http://127.0.0.1:8080
En Vercel:         Vercel detecta Flask y usa la variable `app` de este archivo.

Variables de entorno: DATABASE_URL y SECRET_KEY (ver .env.example).
"""
import os
import secrets
import threading
import webbrowser
from datetime import datetime

from flask import Flask, g, redirect, url_for

import reglas
from auth import bp as bp_auth, usuario_actual
from db import CARPETA, cargar_env, obtener_bd
from rutas.caja import bp as bp_caja
from rutas.catalogo import bp as bp_catalogo
from rutas.reportes import bp as bp_reportes
from rutas.usuarios import bp as bp_usuarios
from rutas.ventas import bp as bp_ventas
from seed import USUARIOS as USUARIOS_DEMO

PUERTO = 8080
EN_VERCEL = bool(os.environ.get("VERCEL"))  # Vercel define esta variable en sus servidores


def _clave_secreta():
    """SECRET_KEY firma la cookie de sesión. Nunca se escribe en el código."""
    clave = os.environ.get("SECRET_KEY")
    if clave:
        return clave
    if EN_VERCEL:
        raise RuntimeError("Falta la variable SECRET_KEY en Vercel (Settings → Environment Variables).")
    # En el computador, sin SECRET_KEY se usa una clave temporal: las sesiones
    # se cierran cada vez que se reinicia la aplicación.
    print("Aviso: falta SECRET_KEY en .env; se usa una clave temporal.")
    return secrets.token_hex(32)


def crear_app(url_bd=None, esquema=None):
    # Los archivos estáticos están en public/static: en Vercel los sirve su CDN
    # desde public/ y en el computador los sirve Flask, con la misma URL /static/...
    app = Flask(__name__, static_folder=str(CARPETA / "public" / "static"), static_url_path="/static")
    app.config["SECRET_KEY"] = _clave_secreta()
    app.config["DATABASE_URL"] = url_bd or os.environ.get("DATABASE_URL")
    app.config["ESQUEMA_BD"] = esquema  # solo lo usan las pruebas
    if not app.config["DATABASE_URL"]:
        raise RuntimeError("Falta la variable DATABASE_URL (vea .env.example).")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = EN_VERCEL  # en Vercel todo va por HTTPS

    @app.teardown_appcontext
    def cerrar_bd(_error):
        """Cierra la conexión al terminar cada petición."""
        bd = g.pop("bd", None)
        if bd is not None:
            bd.close()

    # ---- Filtros para las plantillas ----
    app.jinja_env.filters["pesos"] = reglas.pesos
    # Umbral de color de las diferencias del cierre (disponible en plantillas y macros).
    app.jinja_env.globals["umbral_diferencia"] = reglas.UMBRAL_DIFERENCIA_LEVE
    # Cuentas de demostración para el recuadro del inicio de sesión (definidas en seed.py).
    app.jinja_env.globals["cuentas_demo"] = [(rol, usuario, clave) for _, usuario, clave, rol in USUARIOS_DEMO]

    @app.template_filter("cop")
    def cop(n):
        """Pesos con signo menos tipográfico, como lo usa la capa visual: -2000 -> '−$2.000'."""
        n = round(n or 0)
        return ("−$" if n < 0 else "$") + f"{abs(n):,}".replace(",", ".")

    @app.template_filter("fecha")
    def formato_fecha(texto):
        """'2026-11-11' -> '11/11/2026'."""
        try:
            return datetime.strptime(texto, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return texto or ""

    # Variables disponibles en todas las plantillas (usuario y estado de la caja).
    @app.context_processor
    def datos_comunes():
        usuario = usuario_actual()
        caja = reglas.cierre_abierto(obtener_bd()) if usuario else None
        return {"usuario": usuario, "caja_abierta": caja}

    for bp in (bp_auth, bp_caja, bp_ventas, bp_catalogo, bp_reportes, bp_usuarios):
        app.register_blueprint(bp)

    @app.route("/")
    def inicio():
        """Si hay caja abierta va a vender; si no, a abrir la caja."""
        if usuario_actual() is None:
            return redirect(url_for("auth.login"))
        if reglas.cierre_abierto(obtener_bd()):
            return redirect(url_for("ventas.nueva"))
        return redirect(url_for("caja.abrir"))

    return app


# En el computador lee el archivo .env; en Vercel las variables vienen del panel.
cargar_env()

# Vercel busca una variable llamada `app` en este archivo.
app = crear_app()


if __name__ == "__main__":
    # La primera vez crea las tablas y carga la demo en la base de .env.
    from db import conectar, tablas_creadas, url_directa
    con = conectar(url_directa())
    try:
        vacia = not tablas_creadas(con)
    finally:
        con.close()
    if vacia:
        import seed
        print("La base está vacía: se crean las tablas y se cargan los datos de demo...")
        seed.main([])
    url = f"http://127.0.0.1:{PUERTO}"
    print(f"\n  El Fogón Bumangués está funcionando en {url}")
    print("  Para apagarlo, cierre esta ventana o presione Ctrl + C.\n")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=PUERTO, debug=False)  # debug siempre apagado
