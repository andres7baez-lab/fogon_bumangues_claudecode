"""Reglas de negocio de El Fogón Bumangués.

Este archivo no depende de Flask: solo recibe una conexión a la base y
datos sencillos. Así las reglas se pueden probar de forma automática y
se pueden explicar sin mirar las pantallas.

Cada función indica entre corchetes la regla del documento que aplica.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from db import transaccion

# Hora oficial de Colombia. En Vercel el servidor está en UTC (5 horas
# adelante): sin esto, una venta de las 8 p. m. quedaría con la fecha de mañana.
ZONA_HORARIA = ZoneInfo("America/Bogota")

# Número de identificación del cliente genérico (convención DIAN para
# "consumidor final").
ID_CONSUMIDOR_FINAL = "222222222222"
TURNOS = ("almuerzo", "noche")

# Colores de la diferencia en el cierre de caja (solo presentación):
#   0 pesos -> verde · hasta este valor (en valor absoluto) -> amarillo · más -> rojo.
# Cambie solo este número para ajustar la tolerancia.
UMBRAL_DIFERENCIA_LEVE = 2000
CATEGORIAS = ("almuerzo", "bebida", "otro")


class ErrorNegocio(Exception):
    """Error que se le muestra al usuario tal cual (en español)."""


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------
def pesos(valor):
    """Formatea un entero como pesos colombianos: 13500 -> '$13.500'."""
    valor = int(valor or 0)
    signo = "-" if valor < 0 else ""
    return f"{signo}${abs(valor):,}".replace(",", ".")


def a_entero(texto, campo, minimo=0):
    """Convierte lo que escribe el usuario ('13.500', '$13500') en entero."""
    if isinstance(texto, int):
        valor = texto
    else:
        limpio = str(texto or "").strip().replace("$", "").replace(".", "").replace(" ", "")
        if limpio == "":
            limpio = "0"
        if not limpio.lstrip("-").isdigit():
            raise ErrorNegocio(f"El valor de «{campo}» debe ser un número entero, sin decimales.")
        valor = int(limpio)
    if valor < minimo:
        raise ErrorNegocio(f"El valor de «{campo}» no puede ser menor que {pesos(minimo)}.")
    return valor


def ahora_colombia():
    """Fecha y hora actuales en Colombia (sin zona, para formatear como texto)."""
    return datetime.now(ZONA_HORARIA).replace(tzinfo=None)


def _ahora(ahora=None):
    return ahora or ahora_colombia()


# ---------------------------------------------------------------------
# Totales  [Regla 2]
# ---------------------------------------------------------------------
def subtotal(linea):
    """Subtotal de una línea = cantidad x precio_unitario (no se guarda)."""
    return int(linea["cantidad"]) * int(linea["precio_unitario"])


def calcular_total(lineas):
    """valor_total = suma de los subtotales de las líneas."""
    return sum(subtotal(l) for l in lineas)


# ---------------------------------------------------------------------
# Caja: apertura  [Regla 8]
# ---------------------------------------------------------------------
def cierre_abierto(con):
    """Devuelve el cierre de caja abierto, o None si la caja está cerrada."""
    return con.execute(
        "SELECT * FROM CIERRE_CAJA WHERE estado = 'abierto' ORDER BY id_cierre DESC LIMIT 1"
    ).fetchone()


def abrir_caja(con, fecha, turno, base_inicial, id_usuario, hora=None):
    """Abre una jornada de caja. Solo puede haber una caja abierta a la vez."""
    if cierre_abierto(con):
        raise ErrorNegocio("Ya hay una caja abierta. Ciérrela antes de abrir otra.")
    if turno not in TURNOS:
        raise ErrorNegocio("El turno debe ser «almuerzo» o «noche».")
    try:
        datetime.strptime(fecha, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ErrorNegocio("La fecha no es válida.")
    base = a_entero(base_inicial, "base inicial")
    existe = con.execute(
        "SELECT 1 FROM CIERRE_CAJA WHERE fecha = %s AND turno = %s", (fecha, turno)
    ).fetchone()
    if existe:
        raise ErrorNegocio(f"Ya existe una caja para el {fecha} en el turno «{turno}». No se puede abrir dos veces.")
    hora = hora or _ahora().strftime("%H:%M")
    return con.execute(
        """INSERT INTO CIERRE_CAJA (fecha, turno, hora_apertura, base_inicial, estado, id_usuario)
           VALUES (%s, %s, %s, %s, 'abierto', %s) RETURNING id_cierre""",
        (fecha, turno, hora, base, id_usuario),
    ).fetchone()[0]


# ---------------------------------------------------------------------
# Clientes  [Regla 9]
# ---------------------------------------------------------------------
def id_consumidor_final(con):
    fila = con.execute(
        "SELECT id_cliente FROM CLIENTE WHERE numero_identificacion = %s", (ID_CONSUMIDOR_FINAL,)
    ).fetchone()
    if fila is None:
        raise ErrorNegocio("Falta el cliente «Consumidor final». Ejecute el script de datos iniciales.")
    return fila["id_cliente"]


def obtener_o_crear_cliente(con, numero_identificacion=None, nombre=None):
    """Sin datos -> Consumidor final. Con cédula -> busca el cliente o lo crea."""
    numero = (numero_identificacion or "").strip()
    nombre = (nombre or "").strip()
    if not numero:
        return id_consumidor_final(con)
    fila = con.execute(
        "SELECT id_cliente FROM CLIENTE WHERE numero_identificacion = %s", (numero,)
    ).fetchone()
    if fila:
        return fila["id_cliente"]
    if not nombre:
        raise ErrorNegocio("El cliente con ese número no existe. Escriba también su nombre para registrarlo.")
    return con.execute(
        "INSERT INTO CLIENTE (numero_identificacion, nombre) VALUES (%s, %s) RETURNING id_cliente",
        (numero, nombre),
    ).fetchone()[0]


# ---------------------------------------------------------------------
# Ventas  [Reglas 1, 2, 3, 4, 5, 6, 8]
# ---------------------------------------------------------------------
def metodos_pago(con):
    """Diccionario {'efectivo': id, 'transferencia': id}."""
    return {f["nombre"]: f["id_metodo"] for f in con.execute("SELECT * FROM METODO_PAGO")}


def _preparar_lineas(con, lineas):
    """Valida las líneas y les pone el precio vigente del catálogo [Reglas 1, 4, 5, 6]."""
    if not lineas:
        raise ErrorNegocio("La venta no tiene productos.")
    preparadas = []
    for linea in lineas:
        producto = con.execute(
            "SELECT * FROM PRODUCTO WHERE id_producto = %s", (linea.get("id_producto"),)
        ).fetchone()
        if producto is None:
            raise ErrorNegocio("Uno de los productos no existe.")
        if not producto["activo"]:
            raise ErrorNegocio(f"«{producto['nombre']}» no está disponible hoy.")
        cantidad = a_entero(linea.get("cantidad", 1), "cantidad", minimo=1)

        # [Regla 4] El principio solo aplica a productos que lo incluyen y nunca a bebidas.
        lleva_principio = producto["incluye_principio"] == 1 and producto["categoria"] != "bebida"
        id_principio = linea.get("id_principio") or None
        if lleva_principio:
            if id_principio is None:
                raise ErrorNegocio(f"Escoja el principio para «{producto['nombre']}».")
            principio = con.execute(
                "SELECT * FROM PRINCIPIO WHERE id_principio = %s", (id_principio,)
            ).fetchone()
            if principio is None or not principio["activo"]:
                raise ErrorNegocio("El principio escogido no está disponible hoy.")
        else:
            id_principio = None

        # [Regla 1] Se copia el precio actual del catálogo a la línea de la venta.
        preparadas.append({
            "id_producto": producto["id_producto"],
            "id_principio": id_principio,
            "cantidad": cantidad,
            "precio_unitario": producto["precio_unitario"],
        })
    return preparadas


def _preparar_pagos(con, pagos, total):
    """Valida que la suma de los pagos sea igual al total [Regla 3]."""
    ids = metodos_pago(con)
    preparados = []
    for pago in pagos or []:
        valor = a_entero(pago.get("valor"), "valor del pago")
        if valor == 0:
            continue  # un campo de pago vacío no cuenta como pago
        metodo = pago.get("metodo")
        if metodo not in ids:
            raise ErrorNegocio("El método de pago debe ser efectivo o transferencia.")
        preparados.append({"id_metodo": ids[metodo], "valor": valor})
    if not preparados:
        raise ErrorNegocio("Registre al menos un pago.")
    suma = sum(p["valor"] for p in preparados)
    if suma < total:
        raise ErrorNegocio(f"Los pagos suman {pesos(suma)} y la venta es de {pesos(total)}. Faltan {pesos(total - suma)}.")
    if suma > total:
        raise ErrorNegocio(f"Los pagos suman {pesos(suma)} y la venta es de {pesos(total)}. Sobran {pesos(suma - total)}.")
    return preparados


def registrar_venta(con, lineas, pagos, id_usuario, cliente=None, ahora=None):
    """Registra una venta completa (encabezado, detalle y pagos) en una sola transacción.

    lineas: [{'id_producto': 5, 'id_principio': 1, 'cantidad': 2}, ...]
    pagos:  [{'metodo': 'efectivo', 'valor': 10000}, {'metodo': 'transferencia', 'valor': 3500}]
    cliente: {'numero_identificacion': '...', 'nombre': '...'} o None
    Devuelve el id_venta (consecutivo).
    """
    # [Regla 8] Sin caja abierta no se vende.
    cierre = cierre_abierto(con)
    if cierre is None:
        raise ErrorNegocio("No hay una caja abierta. Abra la caja antes de registrar ventas.")

    lineas = _preparar_lineas(con, lineas)
    total = calcular_total(lineas)  # [Regla 2]
    if total <= 0:
        raise ErrorNegocio("El total de la venta debe ser mayor que cero.")
    pagos = _preparar_pagos(con, pagos, total)  # [Regla 3]

    momento = _ahora(ahora)
    cliente = cliente or {}
    with transaccion(con):
        id_cliente = obtener_o_crear_cliente(con, cliente.get("numero_identificacion"), cliente.get("nombre"))
        id_venta = con.execute(
            """INSERT INTO VENTA (fecha, hora, valor_total, estado, id_cliente, id_usuario, id_cierre)
               VALUES (%s, %s, %s, 'activa', %s, %s, %s) RETURNING id_venta""",
            (momento.strftime("%Y-%m-%d"), momento.strftime("%H:%M"), total,
             id_cliente, id_usuario, cierre["id_cierre"]),
        ).fetchone()[0]
        # [Regla 6] Cada combinación plato + principio es una línea aparte.
        for l in lineas:
            con.execute(
                """INSERT INTO DETALLE_VENTA (id_venta, id_producto, id_principio, cantidad, precio_unitario)
                   VALUES (%s, %s, %s, %s, %s)""",
                (id_venta, l["id_producto"], l["id_principio"], l["cantidad"], l["precio_unitario"]),
            )
        for p in pagos:
            con.execute(
                "INSERT INTO PAGO (id_venta, id_metodo, valor) VALUES (%s, %s, %s)",
                (id_venta, p["id_metodo"], p["valor"]),
            )
    return id_venta


# ---------------------------------------------------------------------
# Anulación  [Regla 7]
# ---------------------------------------------------------------------
def anular_venta(con, id_venta, motivo):
    """Marca la venta como anulada (no la borra). El motivo es obligatorio."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise ErrorNegocio("Escriba el motivo de la anulación.")
    venta = con.execute(
        """SELECT v.*, c.estado AS estado_cierre FROM VENTA v
           JOIN CIERRE_CAJA c ON c.id_cierre = v.id_cierre WHERE v.id_venta = %s""",
        (id_venta,),
    ).fetchone()
    if venta is None:
        raise ErrorNegocio("La venta no existe.")
    if venta["estado"] == "anulada":
        raise ErrorNegocio("Esta venta ya estaba anulada.")
    if venta["estado_cierre"] != "abierto":
        raise ErrorNegocio("No se puede anular una venta de una caja que ya fue cerrada.")
    con.execute(
        "UPDATE VENTA SET estado = 'anulada', motivo_anulacion = %s WHERE id_venta = %s",
        (motivo, id_venta),
    )


# ---------------------------------------------------------------------
# Cierre de caja  [Regla 10]
# ---------------------------------------------------------------------
def calcular_diferencias(base_inicial, efectivo_ventas, transferencias_ventas,
                         efectivo_contado=None, transferencias_registradas=None):
    """Cálculo del cierre (nada de esto se guarda en la base).

    Efectivo esperado            = base inicial + pagos en efectivo de ventas activas
    Diferencia en efectivo       = efectivo contado - efectivo esperado
    Diferencia en transferencias = transferencias registradas - pagos por transferencia de ventas activas

    Diferencia negativa = faltante; positiva = sobrante; cero = cuadra.
    """
    esperado = int(base_inicial) + int(efectivo_ventas)
    resultado = {"efectivo_esperado": esperado,
                 "diferencia_efectivo": None,
                 "diferencia_transferencias": None}
    if efectivo_contado is not None:
        resultado["diferencia_efectivo"] = int(efectivo_contado) - esperado
    if transferencias_registradas is not None:
        resultado["diferencia_transferencias"] = int(transferencias_registradas) - int(transferencias_ventas)
    return resultado


def resumen_cierre(con, id_cierre):
    """Reúne todo lo que se muestra en la pantalla de cierre."""
    cierre = con.execute("SELECT * FROM CIERRE_CAJA WHERE id_cierre = %s", (id_cierre,)).fetchone()
    if cierre is None:
        raise ErrorNegocio("El cierre no existe.")
    conteo = con.execute(
        """SELECT
             SUM(CASE WHEN estado = 'activa'  THEN 1 ELSE 0 END)           AS ventas_activas,
             SUM(CASE WHEN estado = 'anulada' THEN 1 ELSE 0 END)           AS ventas_anuladas,
             COALESCE(SUM(CASE WHEN estado = 'activa'  THEN valor_total END), 0) AS total_vendido,
             COALESCE(SUM(CASE WHEN estado = 'anulada' THEN valor_total END), 0) AS total_anulado
           FROM VENTA WHERE id_cierre = %s""",
        (id_cierre,),
    ).fetchone()
    # Pagos por método, solo de ventas activas [Regla 7: las anuladas no cuentan].
    por_metodo = {"efectivo": 0, "transferencia": 0}
    for fila in con.execute(
        """SELECT m.nombre, SUM(p.valor) AS total FROM PAGO p
           JOIN VENTA v ON v.id_venta = p.id_venta
           JOIN METODO_PAGO m ON m.id_metodo = p.id_metodo
           WHERE v.id_cierre = %s AND v.estado = 'activa'
           GROUP BY m.nombre""",
        (id_cierre,),
    ):
        por_metodo[fila["nombre"]] = fila["total"] or 0

    calculos = calcular_diferencias(
        cierre["base_inicial"], por_metodo["efectivo"], por_metodo["transferencia"],
        cierre["efectivo_contado"], cierre["transferencias_registradas"],
    )
    return {
        "cierre": cierre,
        "ventas_activas": conteo["ventas_activas"] or 0,
        "ventas_anuladas": conteo["ventas_anuladas"] or 0,
        "total_vendido": conteo["total_vendido"],
        "total_anulado": conteo["total_anulado"],
        "efectivo_ventas": por_metodo["efectivo"],
        "transferencias_ventas": por_metodo["transferencia"],
        **calculos,
    }


def cerrar_caja(con, id_cierre, efectivo_contado, transferencias_registradas, hora=None):
    """Registra los valores contados y cierra la caja. Devuelve el resumen final."""
    cierre = con.execute("SELECT * FROM CIERRE_CAJA WHERE id_cierre = %s", (id_cierre,)).fetchone()
    if cierre is None:
        raise ErrorNegocio("El cierre no existe.")
    if cierre["estado"] != "abierto":
        raise ErrorNegocio("Esta caja ya estaba cerrada.")
    contado = a_entero(efectivo_contado, "efectivo contado")
    transferencias = a_entero(transferencias_registradas, "transferencias registradas")
    con.execute(
        """UPDATE CIERRE_CAJA SET hora_cierre = %s, efectivo_contado = %s,
           transferencias_registradas = %s, estado = 'cerrado' WHERE id_cierre = %s""",
        (hora or _ahora().strftime("%H:%M"), contado, transferencias, id_cierre),
    )
    return resumen_cierre(con, id_cierre)


# ---------------------------------------------------------------------
# Catálogo  [Reglas 1, 4, 5]
# ---------------------------------------------------------------------
def crear_producto(con, nombre, categoria, precio_unitario, incluye_principio, activo):
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorNegocio("Escriba el nombre del producto.")
    if categoria not in CATEGORIAS:
        raise ErrorNegocio("La categoría debe ser almuerzo, bebida u otro.")
    precio = a_entero(precio_unitario, "precio")
    # [Regla 4] Solo los almuerzos pueden llevar principio.
    incluye = 1 if (incluye_principio and categoria == "almuerzo") else 0
    activo = 1 if activo else 0
    if activo and precio == 0:
        raise ErrorNegocio("Un producto con precio $0 no se puede activar. Fije primero el precio.")
    return con.execute(
        """INSERT INTO PRODUCTO (nombre, categoria, precio_unitario, incluye_principio, activo)
           VALUES (%s, %s, %s, %s, %s) RETURNING id_producto""",
        (nombre, categoria, precio, incluye, activo),
    ).fetchone()[0]


def cambiar_precio(con, id_producto, precio_unitario):
    """[Regla 1] Cambia el precio del catálogo; las ventas anteriores conservan su precio."""
    producto = con.execute("SELECT * FROM PRODUCTO WHERE id_producto = %s", (id_producto,)).fetchone()
    if producto is None:
        raise ErrorNegocio("El producto no existe.")
    precio = a_entero(precio_unitario, "precio")
    if precio == 0 and producto["activo"]:
        raise ErrorNegocio("Un producto activo no puede quedar con precio $0. Desactívelo primero.")
    con.execute("UPDATE PRODUCTO SET precio_unitario = %s WHERE id_producto = %s", (precio, id_producto))
    return producto["nombre"], precio


def cambiar_activo_producto(con, id_producto, activo):
    producto = con.execute("SELECT * FROM PRODUCTO WHERE id_producto = %s", (id_producto,)).fetchone()
    if producto is None:
        raise ErrorNegocio("El producto no existe.")
    if activo and producto["precio_unitario"] == 0:
        raise ErrorNegocio(f"«{producto['nombre']}» tiene precio $0. Fije el precio antes de activarlo.")
    con.execute("UPDATE PRODUCTO SET activo = %s WHERE id_producto = %s", (1 if activo else 0, id_producto))
    return producto["nombre"]


def crear_principio(con, nombre, activo=True):
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorNegocio("Escriba el nombre del principio.")
    return con.execute("INSERT INTO PRINCIPIO (nombre, activo) VALUES (%s, %s) RETURNING id_principio",
                       (nombre, 1 if activo else 0)).fetchone()[0]


def cambiar_activo_principio(con, id_principio, activo):
    principio = con.execute("SELECT * FROM PRINCIPIO WHERE id_principio = %s", (id_principio,)).fetchone()
    if principio is None:
        raise ErrorNegocio("El principio no existe.")
    con.execute("UPDATE PRINCIPIO SET activo = %s WHERE id_principio = %s", (1 if activo else 0, id_principio))
    return principio["nombre"]


def ventas_de_producto(con, id_producto):
    """Cuántas líneas de venta (activas o anuladas) usan este producto."""
    return con.execute("SELECT COUNT(*) FROM DETALLE_VENTA WHERE id_producto = %s", (id_producto,)).fetchone()[0]


def ventas_de_principio(con, id_principio):
    return con.execute("SELECT COUNT(*) FROM DETALLE_VENTA WHERE id_principio = %s", (id_principio,)).fetchone()[0]


def editar_producto(con, id_producto, nombre, categoria, precio_unitario, incluye_principio, activo):
    """Edita todos los datos del producto. [Regla 1] Las ventas anteriores conservan su precio."""
    if con.execute("SELECT 1 FROM PRODUCTO WHERE id_producto = %s", (id_producto,)).fetchone() is None:
        raise ErrorNegocio("El producto no existe.")
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorNegocio("Escriba el nombre del producto.")
    if categoria not in CATEGORIAS:
        raise ErrorNegocio("La categoría debe ser almuerzo, bebida u otro.")
    precio = a_entero(precio_unitario, "precio")
    incluye = 1 if (incluye_principio and categoria == "almuerzo") else 0  # [Regla 4]
    activo = 1 if activo else 0
    if activo and precio == 0:
        raise ErrorNegocio("Un producto con precio $0 no puede quedar activo. Fije el precio o márquelo inactivo.")
    con.execute(
        """UPDATE PRODUCTO SET nombre = %s, categoria = %s, precio_unitario = %s,
           incluye_principio = %s, activo = %s WHERE id_producto = %s""",
        (nombre, categoria, precio, incluye, activo, id_producto),
    )
    return nombre


def eliminar_producto(con, id_producto):
    """Elimina un producto solo si nunca se ha vendido.

    Si ya tiene ventas no se puede borrar: esas ventas (incluso las anuladas)
    dejarían de saber qué se vendió. En ese caso se debe desactivar.
    """
    producto = con.execute("SELECT * FROM PRODUCTO WHERE id_producto = %s", (id_producto,)).fetchone()
    if producto is None:
        raise ErrorNegocio("El producto no existe.")
    usos = ventas_de_producto(con, id_producto)
    if usos:
        raise ErrorNegocio(f"«{producto['nombre']}» aparece en {usos} línea(s) de venta y no se puede eliminar. "
                           "Desactívelo para que el cajero ya no lo vea.")
    con.execute("DELETE FROM PRODUCTO WHERE id_producto = %s", (id_producto,))
    return producto["nombre"]


def editar_principio(con, id_principio, nombre):
    if con.execute("SELECT 1 FROM PRINCIPIO WHERE id_principio = %s", (id_principio,)).fetchone() is None:
        raise ErrorNegocio("El principio no existe.")
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorNegocio("Escriba el nombre del principio.")
    con.execute("UPDATE PRINCIPIO SET nombre = %s WHERE id_principio = %s", (nombre, id_principio))
    return nombre


def eliminar_principio(con, id_principio):
    """Elimina un principio solo si nunca se ha servido en una venta."""
    principio = con.execute("SELECT * FROM PRINCIPIO WHERE id_principio = %s", (id_principio,)).fetchone()
    if principio is None:
        raise ErrorNegocio("El principio no existe.")
    usos = ventas_de_principio(con, id_principio)
    if usos:
        raise ErrorNegocio(f"«{principio['nombre']}» aparece en {usos} línea(s) de venta y no se puede eliminar. "
                           "Desactívelo para que no aparezca hoy.")
    con.execute("DELETE FROM PRINCIPIO WHERE id_principio = %s", (id_principio,))
    return principio["nombre"]


# ---------------------------------------------------------------------
# Reportes (solo ventas activas)
# ---------------------------------------------------------------------
def ventas_por_plato(con, desde, hasta):
    return con.execute(
        """SELECT p.nombre, p.categoria,
                  SUM(d.cantidad) AS cantidad,
                  SUM(d.cantidad * d.precio_unitario) AS total
           FROM DETALLE_VENTA d
           JOIN VENTA v    ON v.id_venta = d.id_venta
           JOIN PRODUCTO p ON p.id_producto = d.id_producto
           WHERE v.estado = 'activa' AND v.fecha BETWEEN %s AND %s
           GROUP BY p.id_producto
           ORDER BY cantidad DESC, p.nombre""",
        (desde, hasta),
    ).fetchall()


def ventas_por_principio(con, desde, hasta):
    return con.execute(
        """SELECT pr.nombre, SUM(d.cantidad) AS cantidad
           FROM DETALLE_VENTA d
           JOIN VENTA v      ON v.id_venta = d.id_venta
           JOIN PRINCIPIO pr ON pr.id_principio = d.id_principio
           WHERE v.estado = 'activa' AND v.fecha BETWEEN %s AND %s
           GROUP BY pr.id_principio
           ORDER BY cantidad DESC, pr.nombre""",
        (desde, hasta),
    ).fetchall()


def historial_cierres(con, desde, hasta):
    """Lista de cierres con sus diferencias calculadas."""
    ids = [f["id_cierre"] for f in con.execute(
        "SELECT id_cierre FROM CIERRE_CAJA WHERE fecha BETWEEN %s AND %s ORDER BY fecha DESC, turno",
        (desde, hasta),
    )]
    return [resumen_cierre(con, i) for i in ids]
