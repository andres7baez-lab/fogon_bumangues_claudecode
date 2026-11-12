"""Carga los datos del restaurante y la demo en la base PostgreSQL.

Uso (desde la carpeta del proyecto, con el entorno activado):

    python seed.py              Crea lo que falte: usuarios de demo, métodos de pago,
                                cliente genérico, catálogo, principios y los cierres
                                con ventas de los últimos 30 días. Se puede correr
                                varias veces: no duplica nada.
    python seed.py --reset      Borra TODO lo registrado (ventas, pagos, cierres,
                                clientes, usuarios y cambios al catálogo, también lo
                                que hicieron los visitantes) y vuelve a cargar la demo.
    python seed.py --sin-demo   Solo los datos base, sin ventas de ejemplo.

Opciones:
    --env ARCHIVO   Lee las URLs de otro archivo, p. ej. --env .env.produccion
    --si            No pregunta antes de --reset.

Usa DIRECT_URL (conexión directa de Neon); si no existe, la deriva de DATABASE_URL.
Nunca crea un cierre para el día de hoy: así quien abra la demo puede abrir la
caja y vender desde cero.
"""
import argparse
import random
from datetime import timedelta

from werkzeug.security import generate_password_hash

import reglas
from db import cargar_env, conectar, crear_tablas, host_de, transaccion, url_directa

# Cuentas de demostración (se muestran en la pantalla de inicio de sesión).
# Las contraseñas se guardan con hash.
USUARIOS = [
    ("Administrador General", "admin", "FogonAdmin2026", "administrador"),
    ("Cajero Principal", "cajero", "FogonCaja2026", "cajero"),
]

PRINCIPIOS = ["Frijol blanco", "Guiso de calabacín"]

# (nombre, precio, incluye_principio) — menú y precios reales del restaurante.
ALMUERZOS = [
    ("Bandeja paisa", 16000, 0),
    ("Pasta a la boloñesa", 14000, 0),
    ("Callo sudado", 13500, 0),
    ("Rollo de pechuga", 16000, 1),
    ("Bocachico sudado", 16000, 1),
    ("Carne goulash", 13500, 1),
    ("Lengua en salsa", 14000, 1),
    ("Albóndigas", 13500, 1),
    ("Pollo napolitano", 13500, 1),
    ("Carne a la plancha", 13500, 1),
    ("Lomo de cerdo", 14500, 1),
    ("Costillitas de cerdo", 45500, 1),  # PRECIO POR CONFIRMAR (posible error del menú)
    ("Chuleta de cerdo", 16000, 1),
    ("Chatas", 14500, 1),
    ("Carne oreada", 15000, 1),
    ("Punta de anca", 15500, 1),
    ("Alitas apanadas", 13500, 1),
    ("Pechuga ranchera", 15500, 1),
    ("Pechuga a la plancha", 13500, 1),
    ("Carne BBQ", 13500, 1),
    ("Carne al chimichurri", 14500, 1),
    ("Pechuga hawaiana", 15500, 1),
    ("Pechuga miel o BBQ", 13500, 1),
    ("Pechuga gratinada", 15500, 1),
    ("Mojarra", 14500, 1),
    ("Róbalo", 14000, 1),
    ("Róbalo marinero", 15000, 1),
    ("Trucha", 13500, 1),
    ("Trucha marinera", 14500, 1),
    ("Cazuela de bagre", 17000, 1),
    ("Almuerzo con papa a la francesa", 17000, 1),
]

# (nombre, precio) — bebidas, activas.
BEBIDAS = [
    ("Gaseosa personal Postobón", 4500),
    ("Jugo Hit", 4000),
    ("Agua", 3000),
    ("Mr Tea", 4000),
]

OTROS = [("Empaque icopor", 1000)]

# Clientes ficticios que a veces piden ser identificados.
CLIENTES_DEMO = [
    ("1098765432", "María Fernanda Rueda"),
    ("91234567", "Jorge Enrique Pinzón"),
    ("1095811220", "Laura Camila Duarte"),
    ("900123456", "Talleres El Cruce S.A.S."),
]

MOTIVOS_ANULACION = [
    "El cliente cambió de pedido antes de servir",
    "Se registró dos veces por error",
    "El cliente se fue sin recibir el pedido",
    "Plato equivocado en la cuenta",
]

DIAS_DEMO = 30


# ---------------------------------------------------------------------
# Datos base (idempotente: solo inserta lo que falta)
# ---------------------------------------------------------------------
def cargar_datos_base(con):
    """Usuarios, métodos de pago, cliente genérico, principios y productos."""
    with transaccion(con):
        cur = con.cursor()
        # Las cuentas de demo se dejan siempre con su contraseña y rol originales.
        cur.executemany(
            """INSERT INTO USUARIO (nombre, usuario, contrasena, rol) VALUES (%s, %s, %s, %s)
               ON CONFLICT (usuario) DO UPDATE
               SET nombre = EXCLUDED.nombre, contrasena = EXCLUDED.contrasena, rol = EXCLUDED.rol""",
            [(n, u, generate_password_hash(c), r) for n, u, c, r in USUARIOS],
        )
        cur.executemany(
            "INSERT INTO METODO_PAGO (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING",
            [("efectivo",), ("transferencia",)],
        )
        cur.executemany(
            "INSERT INTO CLIENTE (numero_identificacion, nombre) VALUES (%s, %s) "
            "ON CONFLICT (numero_identificacion) DO NOTHING",
            [(reglas.ID_CONSUMIDOR_FINAL, "Consumidor final")],
        )
        # PRINCIPIO y PRODUCTO no tienen columna única: se inserta solo si no existe ese nombre.
        cur.executemany(
            """INSERT INTO PRINCIPIO (nombre, activo) SELECT %s, 1
               WHERE NOT EXISTS (SELECT 1 FROM PRINCIPIO WHERE nombre = %s)""",
            [(n, n) for n in PRINCIPIOS],
        )
        productos = ([(n, "almuerzo", p, i, 1) for n, p, i in ALMUERZOS]
                     + [(n, "bebida", p, 0, 1) for n, p in BEBIDAS]
                     + [(n, "otro", p, 0, 1) for n, p in OTROS])
        # Un producto que ya existe NO se toca: los precios que el administrador
        # cambie desde el catálogo se conservan (solo --reset vuelve a los de aquí).
        cur.executemany(
            """INSERT INTO PRODUCTO (nombre, categoria, precio_unitario, incluye_principio, activo)
               SELECT %s, %s, %s, %s, %s
               WHERE NOT EXISTS (SELECT 1 FROM PRODUCTO WHERE nombre = %s)""",
            [(*p, p[0]) for p in productos],
        )
        # Excepción única: las bebidas que siguen como se cargaron al principio
        # ($0 e inactivas, porque no tenían precio) reciben su precio y se activan.
        # Si el administrador ya les puso precio o las activó, no se cambian.
        cur.executemany(
            """UPDATE PRODUCTO SET precio_unitario = %s, activo = 1
               WHERE nombre = %s AND categoria = 'bebida' AND precio_unitario = 0 AND activo = 0""",
            [(p, n) for n, p in BEBIDAS],
        )


# ---------------------------------------------------------------------
# Demo: cierres y ventas de los últimos 30 días
# ---------------------------------------------------------------------
def _insertar_varios(con, consulta, filas):
    """INSERT ... RETURNING de muchas filas en un solo viaje a la base. Devuelve los id."""
    if not filas:
        return []
    cur = con.cursor()
    cur.executemany(consulta, filas, returning=True)
    ids = []
    while True:
        ids.append(cur.fetchone()[0])
        if not cur.nextset():
            break
    return ids


def _generar_ventas(rng, platos, principios, empaque, clientes):
    """Ventas de un turno: [(hora, lineas, pagos, id_cliente)].

    Las líneas y los pagos cumplen las mismas reglas que valida la aplicación:
    principio solo en platos que lo incluyen [Regla 4], una línea por cada
    combinación plato + principio [Regla 6] y pagos que suman el total [Regla 3].
    """
    ventas = []
    minuto = 11 * 60 + 30 + rng.randint(0, 10)
    for _ in range(rng.randint(8, 14)):
        combinaciones = {}
        for _ in range(rng.choices([1, 2, 3], weights=[6, 3, 1])[0]):
            plato = rng.choice(platos)
            principio = rng.choice(principios)["id_principio"] if plato["incluye_principio"] else None
            clave = (plato["id_producto"], principio)
            combinaciones[clave] = combinaciones.get(clave, 0) + rng.choices([1, 2], weights=[5, 1])[0]
        lineas = [{"id_producto": p, "id_principio": pr, "cantidad": c,
                   "precio_unitario": next(x["precio_unitario"] for x in platos if x["id_producto"] == p)}
                  for (p, pr), c in combinaciones.items()]
        if rng.random() < 0.25:  # pedido para llevar
            lineas.append({"id_producto": empaque["id_producto"], "id_principio": None,
                           "cantidad": rng.choice([1, 1, 2]), "precio_unitario": empaque["precio_unitario"]})
        total = reglas.calcular_total(lineas)  # [Regla 2]

        forma = rng.choices(["efectivo", "transferencia", "mixto"], weights=[11, 5, 4])[0]
        if forma == "mixto":
            efectivo = rng.randint(1, max(1, total // 1000 - 1)) * 1000
            pagos = [("efectivo", efectivo), ("transferencia", total - efectivo)]
        else:
            pagos = [(forma, total)]
        assert sum(v for _, v in pagos) == total  # [Regla 3]

        cliente = rng.choice(clientes) if rng.random() < 0.12 else None
        ventas.append((f"{minuto // 60:02d}:{minuto % 60:02d}", lineas, pagos, cliente))
        minuto += rng.randint(4, 16)
    return ventas


def _diferencia_del_dia(rng, numero_dia):
    """Diferencia en efectivo del cierre: cero, pequeña (amarilla) o grande (roja)."""
    tipo = ["cero", "cero", "leve", "cero", "alta", "cero", "leve"][numero_dia % 7]
    if tipo == "cero":
        return 0
    if tipo == "leve":
        return rng.choice([-1, 1]) * rng.choice([500, 1000, 1500, 2000])
    return rng.choice([-1, 1]) * rng.choice([3000, 5000, 8000, 12000])


def cargar_demo(con, dias=DIAS_DEMO, hoy=None):
    """Crea un cierre (turno almuerzo) por cada uno de los últimos `dias` días, sin hoy.

    Los días que ya tienen cierre se saltan, así que correrlo otra vez no duplica
    nada (y unos días después solo agrega los días que falten).
    Devuelve (cierres creados, ventas creadas).
    """
    hoy = hoy or reglas.ahora_colombia().date()
    id_cajero = con.execute("SELECT id_usuario FROM USUARIO WHERE usuario = 'cajero'").fetchone()[0]
    metodo = reglas.metodos_pago(con)
    platos = con.execute(
        "SELECT * FROM PRODUCTO WHERE categoria = 'almuerzo' AND activo = 1 AND nombre <> 'Costillitas de cerdo'"
    ).fetchall()
    principios = con.execute("SELECT * FROM PRINCIPIO WHERE activo = 1").fetchall()
    empaque = con.execute("SELECT * FROM PRODUCTO WHERE nombre = 'Empaque icopor'").fetchone()
    if not platos or not principios or empaque is None:
        raise SystemExit("Faltan productos o principios activos del catálogo base.")

    with transaccion(con):
        con.cursor().executemany(
            "INSERT INTO CLIENTE (numero_identificacion, nombre) VALUES (%s, %s) "
            "ON CONFLICT (numero_identificacion) DO NOTHING", CLIENTES_DEMO)
    clientes = [f["id_cliente"] for f in con.execute(
        "SELECT id_cliente FROM CLIENTE WHERE numero_identificacion = ANY(%s)", ([n for n, _ in CLIENTES_DEMO],))]
    id_final = reglas.id_consumidor_final(con)
    ya_existen = {f["fecha"] for f in con.execute("SELECT fecha FROM CIERRE_CAJA WHERE turno = 'almuerzo'")}

    cierres = ventas_creadas = 0
    for atras in range(dias, 0, -1):
        dia = hoy - timedelta(days=atras)
        fecha = dia.isoformat()
        if fecha in ya_existen:
            continue
        rng = random.Random(dia.toordinal())  # el mismo día siempre genera las mismas ventas
        base = rng.choice([100000, 120000, 150000])
        ventas = _generar_ventas(rng, platos, principios, empaque, clientes)
        anulada = rng.randrange(len(ventas)) if rng.random() < 0.4 else None  # [Regla 7]

        with transaccion(con):
            id_cierre = con.execute(
                """INSERT INTO CIERRE_CAJA (fecha, turno, hora_apertura, base_inicial, estado, id_usuario)
                   VALUES (%s, 'almuerzo', '11:00', %s, 'abierto', %s) RETURNING id_cierre""",
                (fecha, base, id_cajero),
            ).fetchone()[0]
            ids = _insertar_varios(
                con,
                """INSERT INTO VENTA (fecha, hora, valor_total, estado, motivo_anulacion, id_cliente, id_usuario, id_cierre)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id_venta""",
                [(fecha, hora, reglas.calcular_total(lineas),
                  "anulada" if i == anulada else "activa",
                  rng.choice(MOTIVOS_ANULACION) if i == anulada else None,
                  cliente or id_final, id_cajero, id_cierre)
                 for i, (hora, lineas, _, cliente) in enumerate(ventas)],
            )
            cur = con.cursor()
            cur.executemany(
                """INSERT INTO DETALLE_VENTA (id_venta, id_producto, id_principio, cantidad, precio_unitario)
                   VALUES (%s, %s, %s, %s, %s)""",
                [(id_venta, l["id_producto"], l["id_principio"], l["cantidad"], l["precio_unitario"])
                 for id_venta, (_, lineas, _, _) in zip(ids, ventas) for l in lineas],
            )
            cur.executemany(
                "INSERT INTO PAGO (id_venta, id_metodo, valor) VALUES (%s, %s, %s)",
                [(id_venta, metodo[m], v) for id_venta, (_, _, pagos, _) in zip(ids, ventas) for m, v in pagos],
            )
            # Cierre con los valores "contados": esperado + la diferencia del día [Regla 10].
            resumen = reglas.resumen_cierre(con, id_cierre)
            dif_transf = rng.choice([0] * 8 + [-1000, 2000])
            con.execute(
                """UPDATE CIERRE_CAJA SET hora_cierre = %s, efectivo_contado = %s,
                   transferencias_registradas = %s, estado = 'cerrado' WHERE id_cierre = %s""",
                (f"15:{rng.randint(10, 55):02d}",
                 max(0, resumen["efectivo_esperado"] + _diferencia_del_dia(rng, atras)),
                 max(0, resumen["transferencias_ventas"] + dif_transf), id_cierre),
            )
        cierres += 1
        ventas_creadas += len(ventas)
    return cierres, ventas_creadas


# ---------------------------------------------------------------------
# Reinicio
# ---------------------------------------------------------------------
def vaciar_base(con):
    """Borra todos los datos (no las tablas) y reinicia los consecutivos."""
    con.execute(
        """TRUNCATE PAGO, DETALLE_VENTA, VENTA, CIERRE_CAJA, CLIENTE,
                    PRODUCTO, PRINCIPIO, METODO_PAGO, USUARIO RESTART IDENTITY CASCADE"""
    )


def main(argumentos=None):
    p = argparse.ArgumentParser(description="Carga los datos de El Fogón Bumangués.")
    p.add_argument("--reset", action="store_true", help="borra todo y vuelve a cargar la demo")
    p.add_argument("--sin-demo", action="store_true", help="solo datos base, sin ventas de ejemplo")
    p.add_argument("--env", help="archivo de variables a usar (p. ej. .env.produccion)")
    p.add_argument("--si", action="store_true", help="no pedir confirmación")
    a = p.parse_args(argumentos)

    cargar_env()
    if a.env:
        cargar_env(a.env)
    url = url_directa()
    print(f"Base de datos: {host_de(url)}")
    if a.reset and not a.si:
        r = input("Se borrarán TODAS las ventas, cierres, clientes y cambios al catálogo. ¿Continuar? (s/n): ")
        if r.strip().lower() not in ("s", "si", "sí"):
            print("No se hizo ningún cambio.")
            return

    con = conectar(url)
    try:
        crear_tablas(con)
        if a.reset:
            vaciar_base(con)
            print("Base vaciada.")
        cargar_datos_base(con)
        print("Datos base listos (usuarios de demo, métodos de pago, catálogo y principios).")
        if not a.sin_demo:
            cierres, ventas = cargar_demo(con)
            print(f"Demo: {cierres} cierres nuevos con {ventas} ventas (últimos {DIAS_DEMO} días, sin hoy).")
    finally:
        con.close()
    print("Cuentas de demostración:", "  ".join(f"{u} / {c}" for _, u, c, _ in USUARIOS))


if __name__ == "__main__":
    main()
