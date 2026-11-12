# El Fogón Bumangués — Sistema de ventas y cierre de caja

Prototipo del sistema de ventas y cierre de caja del restaurante **El Fogón Bumangués** (Bucaramanga), desarrollado como proyecto de la asignatura **Sistemas de Información**. El restaurante vende entre 250 y 280 almuerzos diarios; el prototipo permite:

- registrar ventas con pagos en **efectivo, transferencia o mixtos**;
- **anular** ventas sin borrarlas (con motivo obligatorio);
- hacer el **cierre de caja** de cada jornada con el cálculo de diferencias;
- administrar el catálogo (platos, precios, principios del día), los usuarios y consultar reportes.

El menú y los precios son los reales del restaurante. **Las ventas y los cierres de la demo son ficticios.**

| Pieza | Qué se usa | Para qué |
|---|---|---|
| Lenguaje y servidor web | Python 3.12 + Flask 3 | La aplicación y sus pantallas (plantillas Jinja). |
| Base de datos | PostgreSQL en **Neon** (plan gratuito), driver psycopg 3 | Guarda las 9 tablas del modelo relacional. |
| Publicación | **Vercel** (plan gratuito) conectado a **GitHub** | Da el link público para computador y celular. |
| Capa visual | `fogon.css` y `fogon.js` (hechos en Claude Design) | Diseño en celular, tablet y computador. |

---

## 1. Cuentas de demostración

| Rol | Usuario | Contraseña |
|---|---|---|
| Administrador | `admin` | `FogonAdmin2026` |
| Cajero | `cajero` | `FogonCaja2026` |

También se muestran en la pantalla de inicio de sesión. Las contraseñas se guardan **cifradas con hash** en la tabla `USUARIO`.

---

## 2. Variables de entorno

El programa no tiene contraseñas ni direcciones de la base escritas en el código: todo se lee de variables de entorno. En el computador van en un archivo **`.env`** (copia de `.env.example`); en Vercel se pegan en el panel del proyecto. El archivo `.env` **nunca se sube a GitHub** (está en `.gitignore`).

| Variable | Qué valor lleva | Dónde se usa |
|---|---|---|
| `DATABASE_URL` | URL de Neon **con pooler** (el servidor dice `-pooler`). | La aplicación web (en el computador y en Vercel). |
| `DIRECT_URL` | URL de Neon **directa** (sin `-pooler`). | `manage.py init-db` y `seed.py`, para crear tablas y cargar datos. Si falta, se usa `DATABASE_URL` quitándole `-pooler`. |
| `SECRET_KEY` | Texto aleatorio largo. **Distinto** en el computador y en Vercel. | Firma la sesión del navegador. |
| `TEST_DATABASE_URL` | URL de la rama **desarrollo** de Neon. **Nunca** la de producción. | Solo las pruebas automáticas. |

Para generar una `SECRET_KEY` nueva:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### ¿Por qué dos URLs?
Neon entrega dos direcciones para la misma base. La **con pooler** reparte muchas conexiones cortas, que es lo que hace Vercel (cada visita puede correr en un servidor distinto y abre y cierra su propia conexión). La **directa** es una conexión normal, mejor para tareas largas como crear tablas o cargar la demo.

### Ramas de Neon
El proyecto de Neon tiene dos ramas (copias independientes de la base):
- **main** → producción: la usa el link público de Vercel.
- **desarrollo** → el computador local y las pruebas automáticas.

---

## 3. Cómo correrlo en el computador

### Paso 1: instalar Python 3.12 (solo una vez)
- **Windows:** entre a <https://www.python.org/downloads/>, descargue **Python 3.12** e instálelo marcando **"Add python.exe to PATH"**.
- **Mac:** descargue Python 3.12 de la misma página y siga el instalador `.pkg`.

### Paso 2: crear el archivo `.env`
1. En la carpeta del proyecto, copie `.env.example` y renombre la copia como **`.env`**.
2. Ábralo con el Bloc de notas y pegue:
   - en `DATABASE_URL`, la URL **con pooler** de la rama **desarrollo** de Neon;
   - en `DIRECT_URL`, la URL **directa** de la misma rama (o déjela vacía);
   - en `SECRET_KEY`, una clave generada con el comando de la sección 2;
   - en `TEST_DATABASE_URL`, la misma URL de la rama **desarrollo**.
3. Guarde el archivo.

### Paso 3: abrir el programa
- **Windows:** doble clic en **`iniciar_windows.bat`**.
- **Mac:** en la Terminal escriba `bash ` (con espacio), arrastre **`iniciar_mac.command`** y presione Enter.

La primera vez tarda un par de minutos (instala las librerías). Si la base está vacía, crea las tablas y carga la demo sola. El navegador se abre en **http://127.0.0.1:8080**. Para apagarlo, cierre la ventana negra (o `Control + C` en la Terminal).

Con la terminal, lo mismo se hace así:

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python -m pip install -r requirements.txt
```

```bash
.venv\Scripts\python app.py
```

(En Mac use `.venv/bin/python` en lugar de `.venv\Scripts\python`.)

---

## 4. Datos de la demo

```bash
python seed.py
```
Crea lo que falte: usuarios de demo, métodos de pago, cliente «Consumidor final», el menú completo, los principios y **un cierre de caja por cada uno de los últimos 30 días** (zona horaria de Bogotá), con sus ventas. Incluye pagos mixtos, algunas ventas anuladas y cierres que **cuadran** (verde), con **diferencia pequeña** (amarillo, hasta $2.000) y con **diferencia grande** (rojo). **Nunca crea el cierre de hoy**, para que quien abra la demo pueda abrir la caja y vender desde cero.

Se puede correr las veces que se quiera: **no duplica** nada. Si se corre unos días después, solo agrega los días que falten para completar los 30. También devuelve las cuentas `admin` y `cajero` a su contraseña y rol de demo.

**Precios:** `seed.py` **no cambia** los productos que ya existen, así que los precios, nombres y estados que el administrador cambie desde *Catálogo* se conservan. La única excepción son las bebidas **inactivas** que sigan en $0 o que tengan exactamente el precio de `seed.py` (se cargaban inactivas antes de tener precio): reciben su precio y se activan. Una bebida con otro precio no se toca. Por eso, si el administrador desactiva una bebida sin cambiarle el precio, el siguiente `seed.py` la vuelve a activar. Solo `--reset` devuelve todo el catálogo a los precios de `seed.py`.

```bash
python seed.py --reset
```
**Borra todo lo registrado** (ventas, pagos, cierres, clientes, usuarios nuevos y cambios al catálogo, incluido lo que hayan hecho los visitantes) y vuelve a cargar la demo completa. Pide confirmación; con `--si` no pregunta.

**Cuándo usar `--reset`:**
- antes de la sustentación o de compartir el link, para mostrar datos limpios;
- si un visitante cerró la caja de hoy (y ya nadie puede abrir otra con la misma fecha y turno);
- si alguien cambió precios, borró principios o cambió la contraseña de las cuentas de demo;
- si los cierres de la demo ya quedaron muy atrás en el tiempo.

Para apuntar a la base de producción se usa `--env .env.produccion` (sección 5, paso 3). En Windows también está **`reiniciar_datos_windows.bat`** (y `reiniciar_datos_mac.command` en Mac), que hace `--reset` sobre la base del archivo `.env`.

---

## 5. Guía para publicar la demo (paso a paso)

### Paso 1 — Subir el repositorio a GitHub
*(Plataforma: GitHub y su computador.)*
1. Cree una cuenta en <https://github.com> si no tiene, y un repositorio **vacío** (sin README).
2. En la carpeta del proyecto, abra una terminal y ejecute (cambie la dirección por la de su repositorio):

```bash
git remote add origin https://github.com/USUARIO/REPOSITORIO.git
```

```bash
git push -u origin main
```

3. La primera vez se abre una ventana para **iniciar sesión en GitHub**: autorice con su cuenta.
4. Revise en la página del repositorio que **no** aparezcan `.env`, `fogon.db` ni la carpeta `.venv`.

### Paso 2 — Crear la base en Neon y copiar las dos URLs
*(Plataforma: Neon.)*
1. Entre a <https://neon.tech>, cree una cuenta (plan **Free**) y un proyecto. Anote la **región** (por ejemplo *AWS US East 1*).
2. El proyecto ya trae la rama **main** (producción). Cree otra rama llamada **desarrollo** en *Branches → New branch*.
3. En la rama **main**, presione **Connect**:
   - con **Connection pooling** activado, copie la URL → será `DATABASE_URL` de producción;
   - con **Connection pooling** desactivado, copie la URL → será `DIRECT_URL` de producción.
4. Repita en la rama **desarrollo** para el archivo `.env` de su computador (sección 3).

### Paso 3 — Crear las tablas y cargar la demo en Neon (desde su computador)
*(Plataforma: su computador.)*
1. En la carpeta del proyecto cree un archivo **`.env.produccion`** (no se sube a GitHub) con estas dos líneas, usando las URLs de la rama **main**:

```
DATABASE_URL=postgresql://...-pooler...
DIRECT_URL=postgresql://...
```

2. Cree las tablas (se puede repetir sin error):

```bash
.venv\Scripts\python manage.py init-db --env .env.produccion
```

3. Cargue la demo:

```bash
.venv\Scripts\python seed.py --env .env.produccion
```

Ambos comandos muestran el servidor al que se conectaron: confirme que sea el de **main**.

### Paso 4 — Importar el repositorio en Vercel y pegar las variables
*(Plataforma: Vercel.)*
1. Entre a <https://vercel.com> y cree una cuenta con **Continue with GitHub** (plan **Hobby**, gratuito).
2. **Add New… → Project →** busque el repositorio y presione **Import**. La primera vez Vercel pide **instalar su aplicación en GitHub**: autorice el acceso al repositorio.
3. Vercel detecta **Flask** solo (no hace falta `vercel.json`). Deje *Build Command* y *Output Directory* vacíos.
4. Abra **Environment Variables** y agregue:

| Name | Value |
|---|---|
| `DATABASE_URL` | URL **con pooler** de la rama **main** |
| `SECRET_KEY` | una clave nueva generada con el comando de la sección 2 (distinta de la de su `.env`) |

   No agregue `DIRECT_URL` ni `TEST_DATABASE_URL`: la aplicación publicada no las necesita.
5. Presione **Deploy** y espere a que diga *Ready*. Vercel le da el link (por ejemplo `https://fogon-bumangues.vercel.app`).
6. Recomendado: en **Settings → Functions → Function Region** elija la región más cercana a la de Neon (para *AWS US East 1*, `Washington, D.C. (iad1)`). Así cada página carga más rápido.
7. Si después cambia una variable, vaya a **Deployments → ⋯ → Redeploy** para que se aplique.

Cada vez que suba cambios a GitHub (`git push`), Vercel publica la nueva versión solo.

### Paso 5 — Verificar el link
*(Plataforma: el navegador, en computador y en celular.)*
1. Abra el link: debe verse el inicio de sesión con el recuadro **Cuentas de demostración** y el aviso *Prototipo académico*.
2. Entre como **cajero** → **Abrir caja** con la fecha de hoy, turno almuerzo y base de $100.000.
3. **Nueva venta:** agregue un plato con principio, pague una parte en efectivo y use *Completar con transferencia* (pago mixto). Guarde.
4. Salga y entre como **admin** → **Ventas del turno** → *Ver detalle* → **Anular** con un motivo.
5. **Cierre de caja:** escriba el efectivo contado y las transferencias, revise los colores de la diferencia y cierre.
6. **Reportes:** deben verse las ventas de los últimos 30 días y el historial de cierres en verde, amarillo y rojo.
7. Repita el recorrido en el **celular** (menú inferior y cuenta que se desliza desde abajo).
8. Al terminar, deje la demo limpia: `python seed.py --reset --env .env.produccion` (el paso 2 cerró la caja de hoy).

---

## 6. Limitaciones de la demo pública

- **Todos los visitantes comparten la misma base.** Lo que registre uno (ventas, anulaciones, cierres, cambios al catálogo) lo ven todos.
- **Una caja cerrada por un visitante impide abrir otra con la misma fecha y turno** (regla `UNIQUE (fecha, turno)`) hasta reiniciar la demo con `seed.py --reset`. Mientras tanto se puede abrir el otro turno del día.
- Cualquiera puede entrar como administrador: puede cambiar precios o la contraseña de las cuentas de demo. `seed.py` (o `--reset`) las devuelve a su estado original.
- **La primera carga puede tardar unos segundos** si la base estaba inactiva: Neon (plan gratuito) la suspende tras unos minutos sin uso y la despierta con la primera visita.

---

## 7. Qué hace cada pantalla

El menú cambia según el rol y según si la caja está abierta. Siempre se ve si la caja está **abierta** o **cerrada**.

| # | Pantalla | Quién la usa | Qué hace |
|---|---|---|---|
| 1 | **Iniciar sesión** | Todos | Usuario y contraseña. Muestra las cuentas de demostración. |
| 2 | **Abrir caja** | Cajero y administrador | Fecha, turno (almuerzo o noche) y base inicial. Una sola caja abierta a la vez y una sola por fecha y turno. |
| 3 | **Nueva venta** | Cajero y administrador | Platos por categoría con buscador; un botón por principio. Cuenta con − / + y total en vivo. Pagos *Todo efectivo*, *Todo transferencia* o mixto (*Completar con…*). Aviso de cuánto **falta** o **sobra**; no guarda si los pagos no suman el total. *Recibido* calcula las vueltas. Cliente opcional («Consumidor final»). |
| 4 | **Ventas del turno** | Cajero y administrador | Ventas de la caja abierta con resumen. *Ver detalle* muestra líneas, subtotales y pagos; el **administrador** puede **anular** con motivo. |
| 5 | **Cierre de caja** | Administrador | Ventas activas y anuladas, pagos por método y **efectivo esperado**. Se escriben el efectivo contado y las transferencias registradas; la diferencia se muestra en vivo (verde $0, amarillo hasta $2.000, rojo más). |
| 6 | **Catálogo** | Administrador | Crear, editar, activar/desactivar y eliminar productos y principios. Solo se elimina lo que **nunca se ha vendido**. |
| 7 | **Reportes** | Administrador | Ventas por plato, por principio e historial de cierres en un rango de fechas (por defecto, los últimos 30 días). |
| 8 | **Usuarios** | Administrador | Crear usuarios, cambiar contraseñas y roles. |

---

## 8. Reglas de negocio y dónde están en el código

Todas están en **`reglas.py`**, separadas de las pantallas.

| Regla | Cómo se cumple |
|---|---|
| 1. El detalle guarda el precio del momento | `registrar_venta` copia `precio_unitario` del catálogo a `DETALLE_VENTA`. |
| 2. Subtotal calculado, no guardado | `subtotal()` y `calcular_total()`. `DETALLE_VENTA` no tiene columna de subtotal. |
| 3. Pagos = total | `_preparar_pagos` rechaza la venta si la suma no es exacta. La pantalla tampoco deja guardar. |
| 4. Principio solo cuando aplica | `_preparar_lineas`: exige principio si `incluye_principio = 1`; en bebidas queda vacío. |
| 5. El cajero solo ve lo activo | Solo se muestran productos y principios con `activo = 1`; el servidor rechaza los inactivos. |
| 6. Principios distintos = líneas distintas | Cada combinación plato + principio es una línea. |
| 7. Anular, no borrar | `anular_venta` cambia el estado con motivo obligatorio; la base tiene un `CHECK` que lo exige. Las anuladas no suman. |
| 8. Sin cierre abierto no hay ventas | `registrar_venta` liga la venta a la caja abierta (`id_cierre`). |
| 9. Cliente opcional | «Consumidor final» (222222222222) por defecto; una cédula nueva crea el cliente. |
| 10. Diferencias del cierre | `calcular_diferencias()`: esperado = base + efectivo de ventas activas; diferencias = contado − esperado y registradas − transferencias. **No se guardan.** |

---

## 9. Base de datos

- **`schema.sql`** crea las 9 tablas del modelo relacional: `CLIENTE`, `USUARIO`, `PRODUCTO`, `PRINCIPIO`, `METODO_PAGO`, `CIERRE_CAJA`, `VENTA`, `DETALLE_VENTA` y `PAGO` (Postgres guarda los nombres en minúscula).
- Llaves primarias `GENERATED ALWAYS AS IDENTITY`, **llaves foráneas** (Postgres siempre las verifica), `UNIQUE (fecha, turno)` en `CIERRE_CAJA`, `UNIQUE` en `numero_identificacion` y `usuario`, y `CHECK` para roles, categorías, estados, turnos, valores 0/1, montos y formato de fechas y horas.
- Los campos Sí/No (`incluye_principio`, `activo`) se mantienen como **enteros 0/1**, igual que en el modelo.
- Fechas `AAAA-MM-DD` y horas `HH:MM` como texto, en **hora de Colombia** (America/Bogota), aunque el servidor de Vercel esté en otra zona horaria.
- Comando para crear las tablas: `python manage.py init-db` (se puede correr varias veces).
- Para mostrar las tablas en la sustentación: en Neon, **Tables** (o **SQL Editor**) de la rama main.

---

## 10. Pruebas automáticas

Las pruebas corren contra la base de `TEST_DATABASE_URL` (rama **desarrollo**), dentro de un esquema aparte llamado `pruebas` que se borra y se crea en cada prueba: no tocan las tablas normales de esa base.

- `test_reglas.py`: reglas 1, 2, 3, 4, 6, 7, 8 y 10, y la edición y eliminación del catálogo.
- `test_web.py`: permisos por rol, recorrido completo (abrir, vender con pago mixto, anular, cerrar, reportes), catálogo desde la web, colores de la diferencia, solo Efectivo y Transferencia, recuadro de cuentas de demo y aviso de prototipo.
- `test_seed.py`: 30 días sin hoy, pagos mixtos, anuladas y los tres colores, pagos y totales que cuadran, que correr el seed dos veces no duplica, precios sin cambios y `--reset`.

```bash
.venv\Scripts\python -m unittest -v
```

---

## 11. Estructura del proyecto

```
fogon_bumangues/
├── app.py              Aplicación Flask (variable `app` para Vercel; python app.py en local)
├── db.py               Conexión a PostgreSQL (psycopg 3), una por petición
├── reglas.py           Reglas de negocio
├── auth.py             Inicio de sesión y permisos por rol
├── manage.py           python manage.py init-db (crear tablas)
├── seed.py             Datos base y demo de 30 días (--reset para reiniciar)
├── schema.sql          Tablas del modelo relacional (PostgreSQL)
├── rutas/              Pantallas: caja, ventas, catálogo, reportes, usuarios
├── templates/          Plantillas HTML (Jinja) y partials/ de la capa visual
├── public/static/      CSS, JS, íconos y manifest (Vercel los sirve desde su CDN)
├── tests/              Pruebas automáticas
├── .env.example        Plantilla de variables de entorno
├── .python-version     Python 3.12 (la misma versión en local y en Vercel)
├── requirements.txt    Librerías con versión fija
└── iniciar_*/reiniciar_datos_*   Accesos directos para Windows y Mac
```

---

## 12. Decisiones de diseño

1. El campo **"Recibido"** solo calcula las vueltas; en `PAGO` se guarda el valor aplicado a la venta.
2. Solo se anulan **ventas de la caja abierta**.
3. **Una sola caja abierta a la vez.**
4. Un producto con precio $0 no se puede activar.
5. Cerrar caja y anular son **solo del administrador**; `CIERRE_CAJA.id_usuario` es quien **abrió** la caja.
6. **Colores de la diferencia:** verde $0, amarillo hasta $2.000 (valor absoluto), rojo más. El umbral está en la constante `UMBRAL_DIFERENCIA_LEVE` de `reglas.py`.
7. Los archivos estáticos están en `public/static/` porque Vercel recomienda servirlos desde `public/`; Flask usa la misma carpeta en local, así que las direcciones `/static/...` son iguales en ambos.

### Datos por confirmar con el restaurante
- **Costillitas de cerdo — $45.500**: parece un error del menú (los demás platos están entre $13.500 y $17.000).
- **Bebidas**: Gaseosa personal Postobón $4.500, Jugo Hit $4.000, Agua $3.000 y Mr Tea $4.000, activas.

---

## 13. Limitaciones del prototipo

- No hay **facturación electrónica DIAN**, **conexión con bancos**, **domicilios**, **inventario** ni **impresión de tiquetes** (fuera del alcance acordado).
- No guarda **quién anuló** una venta ni **quién cerró** la caja.
- Una venta guardada **no se edita** (se anula y se registra de nuevo) y una caja cerrada **no se reabre**.
- Sin **copias de seguridad** propias más allá de las que ofrezca Neon en su plan.
- Seguridad básica: no hay límite de intentos de inicio de sesión, recuperación de contraseña ni registro de auditoría.
- Las fuentes (Kaushan Script y Barlow) vienen de Google Fonts; sin ellas se usan las del sistema.
