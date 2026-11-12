"""Pruebas de los datos de demo (seed.py): idempotencia, fechas y reinicio."""
import unittest
from datetime import timedelta

import reglas
import seed
from tests.apoyo import preparar_base

TABLAS = ("USUARIO", "METODO_PAGO", "CLIENTE", "PRODUCTO", "PRINCIPIO", "CIERRE_CAJA", "VENTA", "DETALLE_VENTA", "PAGO")


class DatosDeDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Una sola carga de 30 días para todas las pruebas de esta clase.
        cls.con = preparar_base(dias_demo=seed.DIAS_DEMO)
        cls.hoy = reglas.ahora_colombia().date()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def conteos(self):
        return {t: self.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLAS}

    def test_30_dias_sin_hoy(self):
        fechas = sorted(f[0] for f in self.con.execute("SELECT fecha FROM CIERRE_CAJA"))
        self.assertEqual(len(fechas), seed.DIAS_DEMO)
        self.assertEqual(fechas[0], (self.hoy - timedelta(days=seed.DIAS_DEMO)).isoformat())
        self.assertEqual(fechas[-1], (self.hoy - timedelta(days=1)).isoformat())
        self.assertNotIn(self.hoy.isoformat(), fechas)
        self.assertIsNone(reglas.cierre_abierto(self.con))  # todos quedan cerrados

    def test_hay_pagos_mixtos_anuladas_y_los_tres_colores(self):
        mixtas = self.con.execute(
            "SELECT COUNT(*) FROM (SELECT id_venta FROM PAGO GROUP BY id_venta HAVING COUNT(*) > 1) x").fetchone()[0]
        anuladas = self.con.execute("SELECT COUNT(*) FROM VENTA WHERE estado = 'anulada'").fetchone()[0]
        self.assertGreater(mixtas, 0)
        self.assertGreater(anuladas, 0)
        hoy = self.hoy.isoformat()
        difs = [abs(r["diferencia_efectivo"]) for r in reglas.historial_cierres(self.con, "2000-01-01", hoy)]
        u = reglas.UMBRAL_DIFERENCIA_LEVE
        self.assertTrue(any(d == 0 for d in difs), "falta un cierre que cuadre (verde)")
        self.assertTrue(any(0 < d <= u for d in difs), "falta una diferencia pequeña (amarillo)")
        self.assertTrue(any(d > u for d in difs), "falta una diferencia grande (rojo)")

    def test_pagos_suman_el_total_de_cada_venta(self):  # Regla 3
        malas = self.con.execute(
            """SELECT COUNT(*) FROM VENTA v
               WHERE v.valor_total <> (SELECT SUM(valor) FROM PAGO p WHERE p.id_venta = v.id_venta)
                  OR v.valor_total <> (SELECT SUM(cantidad * precio_unitario) FROM DETALLE_VENTA d
                                       WHERE d.id_venta = v.id_venta)""").fetchone()[0]
        self.assertEqual(malas, 0)

    def test_correr_dos_veces_no_duplica(self):
        antes = self.conteos()
        seed.cargar_datos_base(self.con)
        self.assertEqual(seed.cargar_demo(self.con), (0, 0))
        self.assertEqual(self.conteos(), antes)

    def test_precios_del_catalogo_sin_cambios(self):
        precios = {f["nombre"]: f["precio_unitario"] for f in self.con.execute("SELECT * FROM PRODUCTO")}
        for nombre, precio, _ in seed.ALMUERZOS:
            self.assertEqual(precios[nombre], precio, nombre)
        self.assertEqual(precios["Costillitas de cerdo"], 45500)

    def test_bebidas_con_precio_y_activas(self):
        for nombre, precio in seed.BEBIDAS:
            p = self.con.execute("SELECT * FROM PRODUCTO WHERE nombre = %s", (nombre,)).fetchone()
            self.assertEqual((p["precio_unitario"], p["activo"], p["categoria"]), (precio, 1, "bebida"), nombre)


class SeedRespetaElCatalogo(unittest.TestCase):
    def setUp(self):
        self.con = preparar_base()

    def tearDown(self):
        self.con.close()

    def precio_activo(self, nombre):
        return tuple(self.con.execute(
            "SELECT precio_unitario, activo FROM PRODUCTO WHERE nombre = %s", (nombre,)).fetchone())

    def test_no_sobrescribe_precios_cambiados_por_el_administrador(self):
        self.con.execute("UPDATE PRODUCTO SET precio_unitario = 17000 WHERE nombre = 'Bandeja paisa'")
        self.con.execute("UPDATE PRODUCTO SET precio_unitario = 5000 WHERE nombre = 'Jugo Hit'")
        self.con.execute("UPDATE PRODUCTO SET precio_unitario = 4200, activo = 0 WHERE nombre = 'Mr Tea'")
        self.con.execute("UPDATE PRODUCTO SET activo = 0 WHERE nombre = 'Bandeja paisa'")
        seed.cargar_datos_base(self.con)
        self.assertEqual(self.precio_activo("Bandeja paisa"), (17000, 0))
        self.assertEqual(self.precio_activo("Jugo Hit"), (5000, 1))
        self.assertEqual(self.precio_activo("Mr Tea"), (4200, 0))  # otro precio: decisión del administrador

    def test_bebidas_viejas_en_cero_reciben_su_precio(self):
        # Así quedaron las bases cargadas antes de tener los precios de las bebidas.
        self.con.execute("UPDATE PRODUCTO SET precio_unitario = 0, activo = 0 WHERE categoria = 'bebida'")
        seed.cargar_datos_base(self.con)
        for nombre, precio in seed.BEBIDAS:
            self.assertEqual(self.precio_activo(nombre), (precio, 1), nombre)

    def test_bebidas_con_precio_pero_inactivas_se_activan(self):
        # Caso de la base de producción: el precio se guardó pero no se activaron.
        for nombre, precio in seed.BEBIDAS:
            self.con.execute("UPDATE PRODUCTO SET precio_unitario = %s, activo = 0 WHERE nombre = %s", (precio, nombre))
        seed.cargar_datos_base(self.con)
        for nombre, precio in seed.BEBIDAS:
            self.assertEqual(self.precio_activo(nombre), (precio, 1), nombre)


class ReinicioDeLaDemo(unittest.TestCase):
    def test_reset_borra_lo_de_los_visitantes(self):
        con = preparar_base(dias_demo=2)
        try:
            id_cajero = con.execute("SELECT id_usuario FROM USUARIO WHERE usuario = 'cajero'").fetchone()[0]
            hoy = reglas.ahora_colombia().date().isoformat()
            reglas.abrir_caja(con, hoy, "almuerzo", 0, id_cajero)     # un visitante abre la caja de hoy
            con.execute("UPDATE USUARIO SET rol = 'cajero' WHERE usuario = 'admin'")  # y daña la cuenta admin
            con.execute("UPDATE PRODUCTO SET precio_unitario = 9999, activo = 0 WHERE nombre = 'Agua'")
            seed.vaciar_base(con)
            seed.cargar_datos_base(con)
            seed.cargar_demo(con, dias=2)
            fechas = [f[0] for f in con.execute("SELECT fecha FROM CIERRE_CAJA")]
            self.assertNotIn(hoy, fechas)
            self.assertEqual(len(fechas), 2)
            rol = con.execute("SELECT rol FROM USUARIO WHERE usuario = 'admin'").fetchone()[0]
            self.assertEqual(rol, "administrador")
            agua = con.execute("SELECT precio_unitario, activo FROM PRODUCTO WHERE nombre = 'Agua'").fetchone()
            self.assertEqual(tuple(agua), (3000, 1))  # --reset vuelve a los precios del seed
            self.assertEqual(con.execute("SELECT MIN(id_venta) FROM VENTA").fetchone()[0], 1)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
