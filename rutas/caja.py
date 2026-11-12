"""Apertura y cierre de caja."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import reglas
from auth import admin_requerido, login_requerido, usuario_actual
from db import obtener_bd
from rutas.ventas import pagos_por_venta

bp = Blueprint("caja", __name__, url_prefix="/caja")


@bp.route("/abrir", methods=["GET", "POST"])
@login_requerido
def abrir():
    bd = obtener_bd()
    if reglas.cierre_abierto(bd):
        return redirect(url_for("ventas.nueva"))
    ahora = reglas.ahora_colombia()
    datos = {
        "fecha": ahora.date().isoformat(),
        # Antes de las 5 p. m. se propone el turno de almuerzo.
        "turno": "almuerzo" if ahora.hour < 17 else "noche",
        "base_inicial": "",
    }
    if request.method == "POST":
        datos = {k: request.form.get(k, "") for k in datos}
        try:
            reglas.abrir_caja(bd, datos["fecha"], datos["turno"], datos["base_inicial"],
                              usuario_actual()["id_usuario"])
            flash("Caja abierta. Ya puede registrar ventas.", "ok")
            return redirect(url_for("ventas.nueva"))
        except reglas.ErrorNegocio as e:
            flash(str(e), "error")
    return render_template("abrir_caja.html", datos=datos)


@bp.route("/cerrar")
@admin_requerido
def cerrar():
    cierre = reglas.cierre_abierto(obtener_bd())
    if cierre is None:
        flash("No hay una caja abierta para cerrar.", "info")
        return redirect(url_for("reportes.inicio"))
    return redirect(url_for("caja.detalle", id_cierre=cierre["id_cierre"]))


@bp.route("/<int:id_cierre>", methods=["GET", "POST"])
@admin_requerido
def detalle(id_cierre):
    """Resumen de una caja. Si está abierta, permite cerrarla."""
    bd = obtener_bd()
    try:
        resumen = reglas.resumen_cierre(bd, id_cierre)
    except reglas.ErrorNegocio:
        abort(404)
    if request.method == "POST":
        try:
            reglas.cerrar_caja(bd, id_cierre, request.form.get("efectivo_contado"),
                               request.form.get("transferencias_registradas"))
            flash("La caja quedó cerrada.", "ok")
            return redirect(url_for("caja.detalle", id_cierre=id_cierre))
        except reglas.ErrorNegocio as e:
            flash(str(e), "error")

    ventas = bd.execute(
        """SELECT v.*, c.nombre AS cliente FROM VENTA v
           LEFT JOIN CLIENTE c ON c.id_cliente = v.id_cliente
           WHERE v.id_cierre = %s ORDER BY v.id_venta DESC""",
        (id_cierre,),
    ).fetchall()
    abrio = bd.execute("SELECT nombre FROM USUARIO WHERE id_usuario = %s",
                       (resumen["cierre"]["id_usuario"],)).fetchone()
    return render_template("cierre.html", r=resumen, c=resumen["cierre"], ventas=ventas,
                           pagos=pagos_por_venta(bd, [v["id_venta"] for v in ventas]),
                           abrio=abrio["nombre"], formulario=request.form)
