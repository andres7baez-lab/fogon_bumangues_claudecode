"""Pantallas de ventas: nueva venta, ventas del turno, detalle y anulación."""
import json

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import reglas
from auth import admin_requerido, login_requerido, usuario_actual
from db import obtener_bd

bp = Blueprint("ventas", __name__, url_prefix="/ventas")


def _catalogo_activo(bd):
    """Productos y principios activos [Regla 5: el cajero solo ve lo activo]."""
    productos = [dict(p) for p in bd.execute(
        """SELECT id_producto, nombre, categoria, precio_unitario, incluye_principio
           FROM PRODUCTO WHERE activo = 1
           ORDER BY CASE categoria WHEN 'almuerzo' THEN 1 WHEN 'bebida' THEN 2 ELSE 3 END, nombre"""
    )]
    for p in productos:
        # [Regla 4] Las bebidas nunca llevan principio.
        p["lleva_principio"] = bool(p["incluye_principio"]) and p["categoria"] != "bebida"
    principios = [dict(p) for p in bd.execute(
        "SELECT id_principio, nombre FROM PRINCIPIO WHERE activo = 1 ORDER BY nombre"
    )]
    return productos, principios


def pagos_por_venta(bd, ids):
    """{id_venta: [{'metodo': 'efectivo', 'valor': 10000}, ...]}"""
    resultado = {i: [] for i in ids}
    if not ids:
        return resultado
    # "= ANY(%s)" recibe la lista completa como un solo parámetro.
    for f in bd.execute(
        """SELECT p.id_venta, m.nombre AS metodo, p.valor FROM PAGO p
           JOIN METODO_PAGO m ON m.id_metodo = p.id_metodo
           WHERE p.id_venta = ANY(%s) ORDER BY p.id_pago""",
        (list(ids),),
    ):
        resultado[f["id_venta"]].append({"metodo": f["metodo"], "valor": f["valor"]})
    return resultado


@bp.route("/nueva", methods=["GET", "POST"])
@login_requerido
def nueva():
    bd = obtener_bd()
    if reglas.cierre_abierto(bd) is None:
        flash("No hay una caja abierta. Abra la caja para empezar a vender.", "error")
        return redirect(url_for("caja.abrir"))

    carrito = []
    formulario = {}
    if request.method == "POST":
        formulario = request.form
        try:
            carrito = json.loads(request.form.get("lineas") or "[]")
        except ValueError:
            carrito = []
        lineas = [{"id_producto": l.get("id_producto"), "id_principio": l.get("id_principio"),
                   "cantidad": l.get("cantidad", 1)} for l in carrito]
        pagos = [
            {"metodo": "efectivo", "valor": request.form.get("pago_efectivo")},
            {"metodo": "transferencia", "valor": request.form.get("pago_transferencia")},
        ]
        cliente = {"numero_identificacion": request.form.get("cliente_numero"),
                   "nombre": request.form.get("cliente_nombre")}
        try:
            id_venta = reglas.registrar_venta(bd, lineas, pagos, usuario_actual()["id_usuario"], cliente)
            venta = bd.execute("SELECT valor_total FROM VENTA WHERE id_venta = %s", (id_venta,)).fetchone()
            mensaje = f"Venta #{id_venta} registrada por {reglas.pesos(venta['valor_total'])}."
            # "Recibido" solo sirve para calcular las vueltas; no se guarda.
            try:
                recibido = reglas.a_entero(request.form.get("recibido"), "recibido")
                efectivo = reglas.a_entero(request.form.get("pago_efectivo"), "efectivo")
                if recibido > efectivo > 0:
                    mensaje += f" Vueltas: {reglas.pesos(recibido - efectivo)}."
            except reglas.ErrorNegocio:
                pass
            flash(mensaje, "ok")
            return redirect(url_for("ventas.nueva"))
        except reglas.ErrorNegocio as e:
            flash(str(e), "error")

    productos, principios = _catalogo_activo(bd)
    return render_template("nueva_venta.html", productos=productos, principios=principios,
                           carrito=carrito, formulario=formulario)


@bp.route("/")
@login_requerido
def lista():
    """Ventas del cierre que está abierto."""
    bd = obtener_bd()
    cierre = reglas.cierre_abierto(bd)
    if cierre is None:
        flash("No hay una caja abierta.", "info")
        return redirect(url_for("caja.abrir"))
    ventas = bd.execute(
        """SELECT v.*, c.nombre AS cliente, u.nombre AS cajero FROM VENTA v
           LEFT JOIN CLIENTE c ON c.id_cliente = v.id_cliente
           JOIN USUARIO u ON u.id_usuario = v.id_usuario
           WHERE v.id_cierre = %s ORDER BY v.id_venta DESC""",
        (cierre["id_cierre"],),
    ).fetchall()
    pagos = pagos_por_venta(bd, [v["id_venta"] for v in ventas])
    resumen = reglas.resumen_cierre(bd, cierre["id_cierre"])
    return render_template("ventas.html", ventas=ventas, pagos=pagos, resumen=resumen, cierre=cierre)


@bp.route("/<int:id_venta>")
@login_requerido
def detalle(id_venta):
    bd = obtener_bd()
    venta = bd.execute(
        """SELECT v.*, c.nombre AS cliente, c.numero_identificacion, u.nombre AS cajero,
                  ci.estado AS estado_cierre, ci.fecha AS fecha_cierre, ci.turno
           FROM VENTA v
           LEFT JOIN CLIENTE c ON c.id_cliente = v.id_cliente
           JOIN USUARIO u ON u.id_usuario = v.id_usuario
           JOIN CIERRE_CAJA ci ON ci.id_cierre = v.id_cierre
           WHERE v.id_venta = %s""",
        (id_venta,),
    ).fetchone()
    if venta is None:
        abort(404)
    lineas = bd.execute(
        """SELECT d.*, p.nombre AS producto, pr.nombre AS principio FROM DETALLE_VENTA d
           JOIN PRODUCTO p ON p.id_producto = d.id_producto
           LEFT JOIN PRINCIPIO pr ON pr.id_principio = d.id_principio
           WHERE d.id_venta = %s ORDER BY d.id_detalle""",
        (id_venta,),
    ).fetchall()
    pagos = pagos_por_venta(bd, [id_venta])[id_venta]
    return render_template("venta_detalle.html", venta=venta, lineas=lineas, pagos=pagos,
                           subtotal=reglas.subtotal)


@bp.route("/<int:id_venta>/anular", methods=["POST"])
@admin_requerido
def anular(id_venta):
    """[Regla 7] Solo el administrador anula, y con motivo obligatorio."""
    try:
        reglas.anular_venta(obtener_bd(), id_venta, request.form.get("motivo"))
        flash(f"La venta #{id_venta} quedó anulada. No se tendrá en cuenta en el cierre.", "ok")
    except reglas.ErrorNegocio as e:
        flash(str(e), "error")
    return redirect(url_for("ventas.detalle", id_venta=id_venta))
