"""Pruebas de las pantallas: permisos por rol y recorrido completo por la web."""
import json
import unittest
from pathlib import Path

from tests.apoyo import ESQUEMA, URL_PRUEBAS, conectar_prueba, preparar_base
from app import crear_app

ADMIN = ("admin", "FogonAdmin2026")
CAJERO = ("cajero", "FogonCaja2026")


def conectar(_ruta=None):
    """Conexión al esquema de pruebas (el argumento se conserva para no cambiar las pruebas)."""
    return conectar_prueba()


class PruebasWeb(unittest.TestCase):
    def setUp(self):
        preparar_base(dias_demo=3).close()  # 3 días de demo bastan y la prueba es más rápida
        self.ruta = None
        self.app = crear_app(URL_PRUEBAS, ESQUEMA)
        self.cliente = self.app.test_client()

    def entrar(self, usuario, clave):
        return self.cliente.post("/login", data={"usuario": usuario, "contrasena": clave}, follow_redirects=True)

    def test_plantillas_no_usan_confirm_del_navegador(self):
        """window.confirm() puede estar bloqueado y devolver "No" sin mostrar nada,
        lo que dejaba el botón «Cerrar caja» sin efecto. Se usa data-confirmar."""
        carpeta = Path(__file__).resolve().parent.parent / "templates"
        for plantilla in carpeta.glob("*.html"):
            self.assertNotIn("confirm(", plantilla.read_text(encoding="utf-8"), plantilla.name)
        self.entrar(*ADMIN)
        self.cliente.post("/caja/abrir", data={"fecha": "2030-01-15", "turno": "almuerzo", "base_inicial": "0"})
        texto = self.cliente.get("/caja/cerrar", follow_redirects=True).get_data(as_text=True)
        self.assertIn('data-confirmar="¿Cerrar la caja?', texto)

    def test_catalogo_editar_y_eliminar_por_la_web(self):
        self.entrar(*ADMIN)
        con = conectar(self.ruta)
        agua = con.execute("SELECT id_producto FROM PRODUCTO WHERE nombre='Agua'").fetchone()[0]
        bandeja = con.execute("SELECT id_producto FROM DETALLE_VENTA ORDER BY id_detalle LIMIT 1").fetchone()[0]
        self.assertEqual(self.cliente.get(f"/catalogo/productos/{agua}/editar").status_code, 200)
        r = self.cliente.post(f"/catalogo/productos/{agua}/editar",
                              data={"nombre": "Agua 600 ml", "categoria": "bebida", "precio_unitario": "3.000",
                                    "incluye_principio": "0", "activo": "1"}, follow_redirects=True)
        self.assertIn("Agua 600 ml", r.get_data(as_text=True))
        r = self.cliente.post(f"/catalogo/productos/{agua}/eliminar", follow_redirects=True)
        self.assertIn("eliminado del catálogo", r.get_data(as_text=True))
        # Un producto que ya tiene ventas en la demo no se elimina.
        r = self.cliente.post(f"/catalogo/productos/{bandeja}/eliminar", follow_redirects=True)
        self.assertIn("no se puede eliminar", r.get_data(as_text=True))
        con.close()

    def test_colores_de_la_diferencia_segun_el_umbral(self):
        import reglas
        u = reglas.UMBRAL_DIFERENCIA_LEVE
        with self.app.test_request_context():
            plantilla = self.app.jinja_env.from_string(
                '{% from "_diferencia.html" import diferencia %}{{ diferencia(v) }}')
            self.assertIn("fg-diff--cero", plantilla.render(v=0))
            self.assertIn("fg-diff--leve", plantilla.render(v=-u))        # justo en el umbral: amarillo
            self.assertIn("fg-diff--leve", plantilla.render(v=u))
            self.assertIn("fg-diff--alta", plantilla.render(v=-(u + 1)))  # pasa el umbral: rojo
            self.assertIn("fg-diff--alta", plantilla.render(v=u + 1))

    def test_solo_efectivo_y_transferencia(self):
        con = conectar(self.ruta)
        metodos = {f[0] for f in con.execute("SELECT nombre FROM METODO_PAGO")}
        con.close()
        self.assertEqual(metodos, {"efectivo", "transferencia"})
        self.entrar(*ADMIN)
        self.cliente.post("/caja/abrir", data={"fecha": "2030-01-15", "turno": "almuerzo", "base_inicial": "0"})
        texto = self.cliente.get("/ventas/nueva").get_data(as_text=True)
        self.assertNotIn("Tarjeta", texto)
        self.assertIn('name="pago_efectivo"', texto)
        self.assertIn('name="pago_transferencia"', texto)

    def test_login_muestra_cuentas_de_demo_y_aviso(self):
        texto = self.cliente.get("/login").get_data(as_text=True)
        self.assertIn("Cuentas de demostración", texto)
        self.assertIn("FogonAdmin2026", texto)
        self.assertIn("FogonCaja2026", texto)
        aviso = "Prototipo académico. Las ventas y los cierres son datos ficticios."
        self.assertIn(aviso, texto)
        self.entrar(*CAJERO)
        self.assertIn(aviso, self.cliente.get("/caja/abrir").get_data(as_text=True))

    def test_bebida_activa_aparece_en_nueva_venta(self):
        con = conectar()
        con.execute("UPDATE PRODUCTO SET activo = 0 WHERE nombre = 'Agua'")  # una inactiva no debe salir
        jugo = con.execute("SELECT * FROM PRODUCTO WHERE nombre = 'Jugo Hit'").fetchone()
        con.close()
        self.assertEqual((jugo["categoria"], jugo["activo"]), ("bebida", 1))
        self.entrar(*CAJERO)
        self.cliente.post("/caja/abrir", data={"fecha": "2030-01-15", "turno": "almuerzo", "base_inicial": "0"})
        texto = self.cliente.get("/ventas/nueva").get_data(as_text=True)
        # Tarjeta de la bebida (sin principio), su sección y el atajo para llegar a ella.
        self.assertIn(f'onclick="agregar({jugo["id_producto"]}, null, this)"', texto)
        self.assertIn('id="cat-bebida"', texto)
        self.assertIn('href="#cat-bebida">Bebidas (3)</a>', texto)
        self.assertNotIn('data-nombre="agua"', texto)
        # Y se puede vender.
        lineas = json.dumps([{"id_producto": jugo["id_producto"], "id_principio": None, "cantidad": 2}])
        r = self.cliente.post("/ventas/nueva", data={"lineas": lineas, "pago_efectivo": "8.000"}, follow_redirects=True)
        self.assertIn("registrada por $8.000", r.get_data(as_text=True))

    def test_contrasena_incorrecta(self):
        r = self.entrar("admin", "mala")
        self.assertIn("incorrectos", r.get_data(as_text=True))

    def test_cajero_no_entra_a_opciones_de_administrador(self):
        self.entrar(*CAJERO)
        for ruta in ("/catalogo/", "/reportes/", "/usuarios/", "/caja/1"):
            r = self.cliente.get(ruta, follow_redirects=True)
            self.assertIn("solo para el administrador", r.get_data(as_text=True), ruta)

    def test_sin_caja_abierta_redirige_a_abrir_caja(self):
        self.entrar(*CAJERO)
        r = self.cliente.get("/ventas/nueva", follow_redirects=True)
        self.assertIn("Abrir caja", r.get_data(as_text=True))

    def test_recorrido_completo(self):
        self.entrar(*ADMIN)
        # 1. Abrir caja
        r = self.cliente.post("/caja/abrir", data={"fecha": "2030-01-15", "turno": "almuerzo", "base_inicial": "50.000"},
                              follow_redirects=True)
        self.assertIn("Caja abierta", r.get_data(as_text=True))
        con = conectar(self.ruta)
        id_cierre = con.execute("SELECT id_cierre FROM CIERRE_CAJA WHERE estado='abierto'").fetchone()[0]
        rollo = con.execute("SELECT id_producto FROM PRODUCTO WHERE nombre='Rollo de pechuga'").fetchone()[0]
        frijol = con.execute("SELECT id_principio FROM PRINCIPIO WHERE nombre='Frijol blanco'").fetchone()[0]

        # 2. Vender con pago mixto
        lineas = json.dumps([{"id_producto": rollo, "id_principio": frijol, "cantidad": 2}])
        r = self.cliente.post("/ventas/nueva", data={"lineas": lineas, "pago_efectivo": "20.000",
                                                     "pago_transferencia": "12.000", "recibido": "50.000"},
                              follow_redirects=True)
        texto = r.get_data(as_text=True)
        self.assertIn("registrada por $32.000", texto)
        self.assertIn("Vueltas: $30.000", texto)

        # 3. Una venta con pagos que no cuadran se rechaza
        r = self.cliente.post("/ventas/nueva", data={"lineas": lineas, "pago_efectivo": "30.000"}, follow_redirects=True)
        self.assertIn("Faltan $2.000", r.get_data(as_text=True))

        # 4. Otra venta y anularla
        self.cliente.post("/ventas/nueva", data={"lineas": lineas, "pago_efectivo": "32.000"})
        id_venta = con.execute("SELECT MAX(id_venta) FROM VENTA").fetchone()[0]
        r = self.cliente.post(f"/ventas/{id_venta}/anular", data={"motivo": "Prueba"}, follow_redirects=True)
        self.assertIn("quedó anulada", r.get_data(as_text=True))

        # 5. Cerrar: esperado = 50.000 + 20.000 = 70.000 ; transferencias = 12.000
        r = self.cliente.post(f"/caja/{id_cierre}", data={"efectivo_contado": "70.000",
                                                          "transferencias_registradas": "12.000"},
                              follow_redirects=True)
        texto = r.get_data(as_text=True)
        self.assertIn("La caja quedó cerrada", texto)
        self.assertIn("$70.000", texto)
        self.assertIn("Cuadra", texto)

        # 6. Reporte con el rango del cierre
        r = self.cliente.get("/reportes/?desde=2000-01-01&hasta=2100-01-01")
        self.assertIn("Rollo de pechuga", r.get_data(as_text=True))
        con.close()


if __name__ == "__main__":
    unittest.main()
