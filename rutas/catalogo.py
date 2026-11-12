"""Catálogo: productos, precios y principios del día (solo administrador)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import reglas
from auth import admin_requerido
from db import obtener_bd

bp = Blueprint("catalogo", __name__, url_prefix="/catalogo")


def _ejecutar(funcion, mensaje_ok):
    """Ejecuta una acción del catálogo y muestra el resultado como aviso."""
    try:
        resultado = funcion()
        flash(mensaje_ok(resultado), "ok")
    except reglas.ErrorNegocio as e:
        flash(str(e), "error")
    # Vuelve a la misma fila de la tabla (ancla tipo "#p12").
    ancla = request.form.get("ancla", "")
    return redirect(url_for("catalogo.productos") + (ancla if ancla.startswith("#") else ""))


@bp.route("/")
@admin_requerido
def productos():
    bd = obtener_bd()
    lista = bd.execute(
        """SELECT * FROM PRODUCTO
           ORDER BY CASE categoria WHEN 'almuerzo' THEN 1 WHEN 'bebida' THEN 2 ELSE 3 END, nombre"""
    ).fetchall()
    principios = bd.execute("SELECT * FROM PRINCIPIO ORDER BY activo DESC, nombre").fetchall()
    # Cuántas veces se ha vendido cada producto/principio: solo los no vendidos se pueden eliminar.
    usos_producto = dict(bd.execute("SELECT id_producto, COUNT(*) FROM DETALLE_VENTA GROUP BY id_producto").fetchall())
    usos_principio = dict(bd.execute(
        "SELECT id_principio, COUNT(*) FROM DETALLE_VENTA WHERE id_principio IS NOT NULL GROUP BY id_principio"
    ).fetchall())
    return render_template("catalogo.html", productos=lista, principios=principios,
                           usos_producto=usos_producto, usos_principio=usos_principio)


@bp.route("/productos/<int:id_producto>/editar", methods=["GET", "POST"])
@admin_requerido
def editar_producto(id_producto):
    bd = obtener_bd()
    producto = bd.execute("SELECT * FROM PRODUCTO WHERE id_producto = %s", (id_producto,)).fetchone()
    if producto is None:
        abort(404)
    datos = dict(producto)
    if request.method == "POST":
        f = request.form
        datos.update(nombre=f.get("nombre", ""), categoria=f.get("categoria"), precio_unitario=f.get("precio_unitario", ""),
                     incluye_principio=1 if f.get("incluye_principio") == "1" else 0,
                     activo=1 if f.get("activo") == "1" else 0)
        try:
            nombre = reglas.editar_producto(bd, id_producto, datos["nombre"], datos["categoria"], datos["precio_unitario"],
                                            datos["incluye_principio"], datos["activo"])
            flash(f"Producto «{nombre}» actualizado. Las ventas anteriores conservan su precio.", "ok")
            return redirect(url_for("catalogo.productos") + f"#p{id_producto}")
        except reglas.ErrorNegocio as e:
            flash(str(e), "error")
    return render_template("editar_producto.html", p=datos, id_producto=id_producto,
                           usos=reglas.ventas_de_producto(bd, id_producto))


@bp.route("/productos/<int:id_producto>/eliminar", methods=["POST"])
@admin_requerido
def eliminar_producto(id_producto):
    return _ejecutar(
        lambda: reglas.eliminar_producto(obtener_bd(), id_producto),
        lambda nombre: f"Producto «{nombre}» eliminado del catálogo.",
    )


@bp.route("/principios/<int:id_principio>/editar", methods=["POST"])
@admin_requerido
def editar_principio(id_principio):
    return _ejecutar(
        lambda: reglas.editar_principio(obtener_bd(), id_principio, request.form.get("nombre")),
        lambda nombre: f"Principio renombrado a «{nombre}».",
    )


@bp.route("/principios/<int:id_principio>/eliminar", methods=["POST"])
@admin_requerido
def eliminar_principio(id_principio):
    return _ejecutar(
        lambda: reglas.eliminar_principio(obtener_bd(), id_principio),
        lambda nombre: f"Principio «{nombre}» eliminado.",
    )


@bp.route("/productos/nuevo", methods=["POST"])
@admin_requerido
def nuevo_producto():
    f = request.form
    return _ejecutar(
        lambda: reglas.crear_producto(obtener_bd(), f.get("nombre"), f.get("categoria"), f.get("precio_unitario"),
                                      f.get("incluye_principio") == "1", f.get("activo") == "1"),
        lambda _id: f"Producto «{f.get('nombre', '').strip()}» creado.",
    )


@bp.route("/productos/<int:id_producto>/precio", methods=["POST"])
@admin_requerido
def precio(id_producto):
    return _ejecutar(
        lambda: reglas.cambiar_precio(obtener_bd(), id_producto, request.form.get("precio_unitario")),
        lambda r: f"Nuevo precio de «{r[0]}»: {reglas.pesos(r[1])}. Las ventas anteriores conservan su precio.",
    )


@bp.route("/productos/<int:id_producto>/activo", methods=["POST"])
@admin_requerido
def activo_producto(id_producto):
    activar = request.form.get("activo") == "1"
    return _ejecutar(
        lambda: reglas.cambiar_activo_producto(obtener_bd(), id_producto, activar),
        lambda nombre: f"«{nombre}» {'activado' if activar else 'desactivado'}.",
    )


@bp.route("/principios/nuevo", methods=["POST"])
@admin_requerido
def nuevo_principio():
    nombre = request.form.get("nombre")
    return _ejecutar(
        lambda: reglas.crear_principio(obtener_bd(), nombre, True),
        lambda _id: f"Principio «{nombre.strip()}» creado y activado para hoy.",
    )


@bp.route("/principios/<int:id_principio>/activo", methods=["POST"])
@admin_requerido
def activo_principio(id_principio):
    activar = request.form.get("activo") == "1"
    return _ejecutar(
        lambda: reglas.cambiar_activo_principio(obtener_bd(), id_principio, activar),
        lambda nombre: f"Principio «{nombre}» {'activado' if activar else 'desactivado'}.",
    )
