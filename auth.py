"""Inicio de sesión y control de permisos por rol."""
from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from db import obtener_bd

bp = Blueprint("auth", __name__)


def usuario_actual():
    """Usuario que inició sesión (o None)."""
    if "usuario_cache" not in g:
        g.usuario_cache = None
        id_usuario = session.get("id_usuario")
        if id_usuario:
            g.usuario_cache = obtener_bd().execute(
                "SELECT id_usuario, nombre, usuario, rol FROM USUARIO WHERE id_usuario = %s", (id_usuario,)
            ).fetchone()
    return g.usuario_cache


def login_requerido(vista):
    """Solo deja entrar a usuarios que iniciaron sesión."""
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if usuario_actual() is None:
            return redirect(url_for("auth.login"))
        return vista(*args, **kwargs)
    return envoltura


def admin_requerido(vista):
    """Solo deja entrar al rol administrador."""
    @wraps(vista)
    @login_requerido
    def envoltura(*args, **kwargs):
        if usuario_actual()["rol"] != "administrador":
            flash("Esta opción es solo para el administrador.", "error")
            return redirect(url_for("inicio"))
        return vista(*args, **kwargs)
    return envoltura


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("contrasena", "")
        fila = obtener_bd().execute("SELECT * FROM USUARIO WHERE usuario = %s", (usuario,)).fetchone()
        if fila and check_password_hash(fila["contrasena"], clave):
            session.clear()
            session["id_usuario"] = fila["id_usuario"]
            return redirect(url_for("inicio"))
        flash("Usuario o contraseña incorrectos.", "error")
    return render_template("login.html")


@bp.route("/salir")
def salir():
    session.clear()
    return redirect(url_for("auth.login"))
