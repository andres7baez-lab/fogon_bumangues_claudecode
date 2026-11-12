"""Pruebas automáticas de las reglas de negocio.

Ejecutar desde la carpeta del proyecto:
    python -m unittest -v

Usan la base Postgres de TEST_DATABASE_URL, en un esquema "pruebas" que se
crea de nuevo antes de cada prueba (ver tests/apoyo.py).
"""
import unittest

from psycopg.errors import CheckViolation

from tests.apoyo import preparar_base
import reglas


class BaseDePrueba(unittest.TestCase):
    """Deja la base de pruebas con los datos iniciales antes de cada prueba."""

    def setUp(self):
        self.con = preparar_base()
        self.id_cajero = self.con.execute("SELECT id_usuario FROM USUARIO WHERE usuario='cajero'").fetchone()[0]
        self.prod = {f["nombre"]: f["id_producto"] for f in self.con.execute("SELECT * FROM PRODUCTO")}
        self.princ = {f["nombre"]: f["id_principio"] for f in self.con.execute("SELECT * FROM PRINCIPIO")}

    def tearDown(self):
        self.con.close()

    def columnas(self, tabla):
        return [f[0] for f in self.con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s", (tabla,))]

    # Ayudas
    def abrir(self, base=100000, fecha="2026-11-11", turno="almuerzo"):
        return reglas.abrir_caja(self.con, fecha, turno, base, self.id_cajero)

    def linea(self, nombre, cantidad=1, principio=None):
        return {"id_producto": self.prod[nombre], "cantidad": cantidad,
                "id_principio": self.princ[principio] if principio else None}

    def vender(self, lineas, pagos):
        return reglas.registrar_venta(self.con, lineas, [{"metodo": m, "valor": v} for m, v in pagos], self.id_cajero)

    def contar(self, tabla):
        return self.con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]


class Regla2CalculoDelTotal(BaseDePrueba):
    def test_total_es_la_suma_de_cantidad_por_precio(self):
        lineas = [{"cantidad": 2, "precio_unitario": 16000}, {"cantidad": 1, "precio_unitario": 1000}]
        self.assertEqual(reglas.calcular_total(lineas), 33000)

    def test_venta_guarda_el_total_calculado(self):
        self.abrir()
        id_venta = self.vender(
            [self.linea("Rollo de pechuga", 2, "Frijol blanco"), self.linea("Empaque icopor", 1)],
            [("efectivo", 33000)])
        total = self.con.execute("SELECT valor_total FROM VENTA WHERE id_venta=%s", (id_venta,)).fetchone()[0]
        self.assertEqual(total, 2 * 16000 + 1000)

    def test_el_subtotal_no_se_guarda_en_la_base(self):
        columnas = self.columnas("detalle_venta")
        self.assertNotIn("subtotal", columnas)

    def test_cambiar_precio_no_altera_ventas_anteriores(self):  # Regla 1
        self.abrir()
        id_venta = self.vender([self.linea("Bandeja paisa")], [("efectivo", 16000)])
        reglas.cambiar_precio(self.con, self.prod["Bandeja paisa"], 18000)
        precio = self.con.execute("SELECT precio_unitario FROM DETALLE_VENTA WHERE id_venta=%s", (id_venta,)).fetchone()[0]
        self.assertEqual(precio, 16000)

    def test_mismo_plato_con_principios_distintos_va_en_lineas_separadas(self):  # Regla 6
        self.abrir()
        id_venta = self.vender([self.linea("Trucha", 1, "Frijol blanco"), self.linea("Trucha", 1, "Guiso de calabacín")],
                               [("efectivo", 27000)])
        n = self.con.execute("SELECT COUNT(*) FROM DETALLE_VENTA WHERE id_venta=%s", (id_venta,)).fetchone()[0]
        self.assertEqual(n, 2)

    def test_principio_obligatorio_y_vacio_cuando_no_aplica(self):  # Regla 4
        self.abrir()
        with self.assertRaises(reglas.ErrorNegocio):
            self.vender([self.linea("Trucha")], [("efectivo", 13500)])
        # A un plato sin principio se le ignora el principio enviado.
        id_venta = self.vender([self.linea("Bandeja paisa", 1, "Frijol blanco")], [("efectivo", 16000)])
        principio = self.con.execute("SELECT id_principio FROM DETALLE_VENTA WHERE id_venta=%s", (id_venta,)).fetchone()[0]
        self.assertIsNone(principio)


class Regla3ValidacionDePagos(BaseDePrueba):
    def setUp(self):
        super().setUp()
        self.abrir()
        self.lineas = [self.linea("Carne a la plancha", 1, "Frijol blanco")]  # $13.500

    def test_pagos_menores_que_el_total_no_se_guardan(self):
        with self.assertRaisesRegex(reglas.ErrorNegocio, "Faltan"):
            self.vender(self.lineas, [("efectivo", 10000)])
        self.assertEqual(self.contar("VENTA"), 0)
        self.assertEqual(self.contar("PAGO"), 0)

    def test_pagos_mayores_que_el_total_no_se_guardan(self):
        with self.assertRaisesRegex(reglas.ErrorNegocio, "Sobran"):
            self.vender(self.lineas, [("efectivo", 20000)])
        self.assertEqual(self.contar("VENTA"), 0)

    def test_venta_sin_pagos_no_se_guarda(self):
        with self.assertRaises(reglas.ErrorNegocio):
            self.vender(self.lineas, [])
        self.assertEqual(self.contar("VENTA"), 0)

    def test_pago_mixto_exacto_se_guarda_con_dos_pagos(self):
        id_venta = self.vender(self.lineas, [("efectivo", 10000), ("transferencia", 3500)])
        pagos = self.con.execute("SELECT valor FROM PAGO WHERE id_venta=%s ORDER BY valor", (id_venta,)).fetchall()
        self.assertEqual([p[0] for p in pagos], [3500, 10000])


class Regla7Anulacion(BaseDePrueba):
    def setUp(self):
        super().setUp()
        self.id_cierre = self.abrir()
        self.id_venta = self.vender([self.linea("Bandeja paisa")], [("efectivo", 16000)])

    def test_motivo_obligatorio(self):
        for motivo in ("", "   ", None):
            with self.assertRaises(reglas.ErrorNegocio):
                reglas.anular_venta(self.con, self.id_venta, motivo)
        estado = self.con.execute("SELECT estado FROM VENTA WHERE id_venta=%s", (self.id_venta,)).fetchone()[0]
        self.assertEqual(estado, "activa")

    def test_anular_no_borra_la_venta(self):
        reglas.anular_venta(self.con, self.id_venta, "Error del cajero")
        venta = self.con.execute("SELECT * FROM VENTA WHERE id_venta=%s", (self.id_venta,)).fetchone()
        self.assertEqual(venta["estado"], "anulada")
        self.assertEqual(venta["motivo_anulacion"], "Error del cajero")
        self.assertEqual(self.contar("DETALLE_VENTA"), 1)
        self.assertEqual(self.contar("PAGO"), 1)

    def test_anulada_no_cuenta_en_el_cierre(self):
        self.vender([self.linea("Callo sudado")], [("efectivo", 13500)])
        reglas.anular_venta(self.con, self.id_venta, "Cliente se fue")
        r = reglas.resumen_cierre(self.con, self.id_cierre)
        self.assertEqual(r["ventas_activas"], 1)
        self.assertEqual(r["total_vendido"], 13500)
        self.assertEqual(r["efectivo_ventas"], 13500)

    def test_no_se_anula_dos_veces(self):
        reglas.anular_venta(self.con, self.id_venta, "Error")
        with self.assertRaises(reglas.ErrorNegocio):
            reglas.anular_venta(self.con, self.id_venta, "Otra vez")

    def test_no_se_anula_en_una_caja_cerrada(self):
        reglas.cerrar_caja(self.con, self.id_cierre, 116000, 0)
        with self.assertRaises(reglas.ErrorNegocio):
            reglas.anular_venta(self.con, self.id_venta, "Tarde")

    def test_la_base_exige_motivo_al_anular(self):
        with self.assertRaises(CheckViolation):
            self.con.execute("UPDATE VENTA SET estado='anulada' WHERE id_venta=%s", (self.id_venta,))


class Regla8VentaSinCierreAbierto(BaseDePrueba):
    def test_no_se_vende_sin_caja_abierta(self):
        with self.assertRaisesRegex(reglas.ErrorNegocio, "No hay una caja abierta"):
            self.vender([self.linea("Bandeja paisa")], [("efectivo", 16000)])
        self.assertEqual(self.contar("VENTA"), 0)

    def test_la_venta_queda_ligada_al_cierre_abierto(self):
        id_cierre = self.abrir()
        id_venta = self.vender([self.linea("Bandeja paisa")], [("efectivo", 16000)])
        ligado = self.con.execute("SELECT id_cierre FROM VENTA WHERE id_venta=%s", (id_venta,)).fetchone()[0]
        self.assertEqual(ligado, id_cierre)

    def test_despues_de_cerrar_no_se_vende(self):
        id_cierre = self.abrir()
        reglas.cerrar_caja(self.con, id_cierre, 100000, 0)
        with self.assertRaises(reglas.ErrorNegocio):
            self.vender([self.linea("Bandeja paisa")], [("efectivo", 16000)])

    def test_no_se_abren_dos_cajas_ni_se_repite_fecha_y_turno(self):
        id_cierre = self.abrir()
        with self.assertRaises(reglas.ErrorNegocio):
            self.abrir(turno="noche")  # ya hay una abierta
        reglas.cerrar_caja(self.con, id_cierre, 100000, 0)
        with self.assertRaises(reglas.ErrorNegocio):
            self.abrir()  # mismo día y turno (UNIQUE fecha, turno)


class Regla10DiferenciasDelCierre(BaseDePrueba):
    def test_calculo_puro(self):
        r = reglas.calcular_diferencias(100000, 30000, 15000, 128000, 15000)
        self.assertEqual(r["efectivo_esperado"], 130000)
        self.assertEqual(r["diferencia_efectivo"], -2000)       # faltante
        self.assertEqual(r["diferencia_transferencias"], 0)     # cuadra
        r = reglas.calcular_diferencias(50000, 0, 20000, 51000, 25000)
        self.assertEqual(r["diferencia_efectivo"], 1000)        # sobrante
        self.assertEqual(r["diferencia_transferencias"], 5000)

    def test_cierre_completo_excluye_anuladas(self):
        id_cierre = self.abrir(base=100000)
        self.vender([self.linea("Bandeja paisa")], [("efectivo", 16000)])
        self.vender([self.linea("Carne a la plancha", 1, "Frijol blanco")], [("efectivo", 10000), ("transferencia", 3500)])
        self.vender([self.linea("Pasta a la boloñesa")], [("transferencia", 14000)])
        anulada = self.vender([self.linea("Callo sudado")], [("efectivo", 13500)])
        reglas.anular_venta(self.con, anulada, "Prueba")

        r = reglas.cerrar_caja(self.con, id_cierre, efectivo_contado=125000, transferencias_registradas=18000)
        # Efectivo esperado = 100.000 + 16.000 + 10.000 = 126.000 (la anulada no suma)
        self.assertEqual(r["efectivo_ventas"], 26000)
        self.assertEqual(r["efectivo_esperado"], 126000)
        self.assertEqual(r["diferencia_efectivo"], -1000)
        # Transferencias de ventas = 3.500 + 14.000 = 17.500
        self.assertEqual(r["transferencias_ventas"], 17500)
        self.assertEqual(r["diferencia_transferencias"], 500)
        self.assertEqual(r["cierre"]["estado"], "cerrado")

    def test_las_diferencias_no_se_guardan_en_la_base(self):
        columnas = self.columnas("cierre_caja")
        for calculado in ("efectivo_esperado", "diferencia_efectivo", "diferencia_transferencias"):
            self.assertNotIn(calculado, columnas)


class CatalogoEditarYEliminar(BaseDePrueba):
    def test_eliminar_producto_sin_ventas(self):
        reglas.eliminar_producto(self.con, self.prod["Agua"])
        self.assertIsNone(self.con.execute("SELECT 1 FROM PRODUCTO WHERE id_producto=%s", (self.prod["Agua"],)).fetchone())

    def test_no_se_elimina_un_producto_con_ventas_ni_anuladas(self):
        self.abrir()
        id_venta = self.vender([self.linea("Bandeja paisa")], [("efectivo", 16000)])
        reglas.anular_venta(self.con, id_venta, "Prueba")
        with self.assertRaisesRegex(reglas.ErrorNegocio, "Desactívelo"):
            reglas.eliminar_producto(self.con, self.prod["Bandeja paisa"])
        self.assertIsNotNone(self.con.execute("SELECT 1 FROM PRODUCTO WHERE id_producto=%s",
                                              (self.prod["Bandeja paisa"],)).fetchone())

    def test_editar_producto_no_cambia_ventas_anteriores(self):
        self.abrir()
        id_venta = self.vender([self.linea("Bandeja paisa")], [("efectivo", 16000)])
        reglas.editar_producto(self.con, self.prod["Bandeja paisa"], "Bandeja paisa especial", "almuerzo", "18.500", False, True)
        p = self.con.execute("SELECT * FROM PRODUCTO WHERE id_producto=%s", (self.prod["Bandeja paisa"],)).fetchone()
        self.assertEqual((p["nombre"], p["precio_unitario"]), ("Bandeja paisa especial", 18500))
        precio = self.con.execute("SELECT precio_unitario FROM DETALLE_VENTA WHERE id_venta=%s", (id_venta,)).fetchone()[0]
        self.assertEqual(precio, 16000)

    def test_editar_valida_precio_cero_activo_y_principio_en_bebidas(self):
        with self.assertRaises(reglas.ErrorNegocio):
            reglas.editar_producto(self.con, self.prod["Agua"], "Agua", "bebida", 0, False, True)
        reglas.editar_producto(self.con, self.prod["Agua"], "Agua", "bebida", 3000, True, True)
        incluye = self.con.execute("SELECT incluye_principio FROM PRODUCTO WHERE id_producto=%s", (self.prod["Agua"],)).fetchone()[0]
        self.assertEqual(incluye, 0)  # una bebida nunca lleva principio (Regla 4)

    def test_principios_editar_y_eliminar(self):
        id_nuevo = reglas.crear_principio(self.con, "Lentejas")
        reglas.editar_principio(self.con, id_nuevo, "Lentejas guisadas")
        reglas.eliminar_principio(self.con, id_nuevo)
        self.assertIsNone(self.con.execute("SELECT 1 FROM PRINCIPIO WHERE id_principio=%s", (id_nuevo,)).fetchone())
        self.abrir()
        self.vender([self.linea("Trucha", 1, "Frijol blanco")], [("efectivo", 13500)])
        with self.assertRaises(reglas.ErrorNegocio):
            reglas.eliminar_principio(self.con, self.princ["Frijol blanco"])


if __name__ == "__main__":
    unittest.main()
