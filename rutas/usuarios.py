"""Gestión de usuarios (solo administrador)."""
from psycopg.errors import UniqueViolation
from flask import Blueprint, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from auth import admin_requerido, usuario_actual
from db import obtener_bd

bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")
ROLES = ("administrador", "cajero")
LARGO_MINIMO_CLAVE = 6


@bp.route("/")
@admin_requerido
def lista():
    usuarios = obtener_bd().execute(
        "SELECT id_usuario, nombre, usuario, rol FROM USUARIO ORDER BY rol, nombre"
    ).fetchall()
    return render_template("usuarios.html", usuarios=usuarios)


@bp.route("/nuevo", methods=["POST"])
@admin_requerido
def nuevo():
    nombre = request.form.get("nombre", "").strip()
    usuario = request.form.get("usuario", "").strip().lower()
    clave = request.form.get("contrasena", "")
    rol = request.form.get("rol")
    if not nombre or not usuario:
        flash("Escriba el nombre y el usuario.", "error")
    elif rol not in ROLES:
        flash("El rol debe ser administrador o cajero.", "error")
    elif len(clave) < LARGO_MINIMO_CLAVE:
        flash(f"La contraseña debe tener al menos {LARGO_MINIMO_CLAVE} caracteres.", "error")
    else:
        try:
            obtener_bd().execute(
                "INSERT INTO USUARIO (nombre, usuario, contrasena, rol) VALUES (%s, %s, %s, %s)",
                (nombre, usuario, generate_password_hash(clave), rol),
            )
            flash(f"Usuario «{usuario}» creado.", "ok")
        except UniqueViolation:
            flash(f"Ya existe un usuario llamado «{usuario}».", "error")
    return redirect(url_for("usuarios.lista"))


@bp.route("/<int:id_usuario>/contrasena", methods=["POST"])
@admin_requerido
def contrasena(id_usuario):
    clave = request.form.get("contrasena", "")
    if len(clave) < LARGO_MINIMO_CLAVE:
        flash(f"La contraseña debe tener al menos {LARGO_MINIMO_CLAVE} caracteres.", "error")
    else:
        obtener_bd().execute("UPDATE USUARIO SET contrasena = %s WHERE id_usuario = %s",
                             (generate_password_hash(clave), id_usuario))
        flash("Contraseña actualizada.", "ok")
    return redirect(url_for("usuarios.lista"))


@bp.route("/<int:id_usuario>/rol", methods=["POST"])
@admin_requerido
def rol(id_usuario):
    nuevo_rol = request.form.get("rol")
    if id_usuario == usuario_actual()["id_usuario"]:
        flash("No puede cambiar su propio rol (así siempre queda al menos un administrador).", "error")
    elif nuevo_rol not in ROLES:
        flash("El rol debe ser administrador o cajero.", "error")
    else:
        obtener_bd().execute("UPDATE USUARIO SET rol = %s WHERE id_usuario = %s", (nuevo_rol, id_usuario))
        flash("Rol actualizado.", "ok")
    return redirect(url_for("usuarios.lista"))
