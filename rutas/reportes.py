"""Reportes: ventas por plato, por principio e historial de cierres (solo administrador)."""
from datetime import datetime, timedelta

from flask import Blueprint, flash, render_template, request

import reglas
from auth import admin_requerido
from db import obtener_bd

bp = Blueprint("reportes", __name__, url_prefix="/reportes")


def _fecha(texto, por_defecto):
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date().isoformat()
    except (TypeError, ValueError):
        return por_defecto


@bp.route("/")
@admin_requerido
def inicio():
    hoy = reglas.ahora_colombia().date()
    desde = _fecha(request.args.get("desde"), (hoy - timedelta(days=30)).isoformat())
    hasta = _fecha(request.args.get("hasta"), hoy.isoformat())
    if desde > hasta:
        flash("La fecha inicial es posterior a la final; se intercambiaron.", "info")
        desde, hasta = hasta, desde
    bd = obtener_bd()
    platos = reglas.ventas_por_plato(bd, desde, hasta)
    principios = reglas.ventas_por_principio(bd, desde, hasta)
    cierres = reglas.historial_cierres(bd, desde, hasta)
    return render_template(
        "reportes.html", desde=desde, hasta=hasta, platos=platos, principios=principios, cierres=cierres,
        total_platos=sum(p["total"] for p in platos),
        unidades=sum(p["cantidad"] for p in platos),
        total_principios=sum(p["cantidad"] for p in principios),
    )
