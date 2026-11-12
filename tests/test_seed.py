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


class ReinicioDeLaDemo(unittest.TestCase):
    def test_reset_borra_lo_de_los_visitantes(self):
        con = preparar_base(dias_demo=2)
        try:
            id_cajero = con.execute("SELECT id_usuario FROM USUARIO WHERE usuario = 'cajero'").fetchone()[0]
            hoy = reglas.ahora_colombia().date().isoformat()
            reglas.abrir_caja(con, hoy, "almuerzo", 0, id_cajero)     # un visitante abre la caja de hoy
            con.execute("UPDATE USUARIO SET rol = 'cajero' WHERE usuario = 'admin'")  # y daña la cuenta admin
            seed.vaciar_base(con)
            seed.cargar_datos_base(con)
            seed.cargar_demo(con, dias=2)
            fechas = [f[0] for f in con.execute("SELECT fecha FROM CIERRE_CAJA")]
            self.assertNotIn(hoy, fechas)
            self.assertEqual(len(fechas), 2)
            rol = con.execute("SELECT rol FROM USUARIO WHERE usuario = 'admin'").fetchone()[0]
            self.assertEqual(rol, "administrador")
            self.assertEqual(con.execute("SELECT MIN(id_venta) FROM VENTA").fetchone()[0], 1)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
