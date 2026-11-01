# iCoope

Plataforma web para la cooperadora escolar: tienda (productos y entradas a eventos), foro de novedades, calendario, transparencia y panel financiero. Backend Flask + MariaDB con API REST y frontend en HTML/CSS/JS.

## 1. Cómo funciona

El sistema usa roles de acceso (RBAC). Los roles se leen de la base de datos en cada request, no del JWT, así que un cambio de rol o una desactivación rige de inmediato.

- **Cooperadora / Admin (Backoffice):** inventario de la tienda, creación de eventos y entradas con aforo, moderación del foro, analíticas de recaudación y publicación de balances. El admin además gestiona usuarios y roles.
- **Clientes (padres, alumnos, docentes):** leen el foro y el calendario sin iniciar sesión. Con sesión, arman un carrito mixto (productos físicos y entradas) y pagan todo en un solo pedido.
- **Staff de eventos:** escanea desde el celular el QR de las entradas para validarlas en la puerta.

### Pagos y tickets

- **Los pagos son simulados.** No hay integración real con Mercado Pago. El cliente usa los botones "Pagar (simulado)" y "Simular rechazo", y existe un webhook simulado protegido por la cabecera `X-Simulation-Key`.
- Al confirmar el carrito se crea el pedido en estado `PENDING` y se **reserva el stock 15 minutos**. Si el pago se rechaza, se cancela o la reserva vence, el stock vuelve solo.
- Si el pago se aprueba y el pedido tiene productos de evento (`es_evento = TRUE`), se genera **un ticket QR por línea del pedido**. El hash es un HMAC-SHA256 sobre `id_usuario:id_detalle` con la sal de la escuela. Una línea con varias entradas comparte un único QR.
- La validación bloquea la fila del ticket: el primer escaneo marca `utilizado = 1` con la hora exacta; los siguientes devuelven 409 con la hora del primer uso (posible clonación).

## 2. Cómo ejecutarlo

Requisitos: Python 3.11+ y MariaDB.

```bash
mysql -u root < backend/db/BasedeDatos.sql
mysql -u root < backend/db/seed.sql          # datos de ejemplo (opcional)

python -m venv .venv
source .venv/bin/activate                    # en Windows: .venv\Scripts\activate
pip install -r requirements.txt

cd backend
flask --app run create-admin                 # crea el primer administrador
python run.py                                # http://127.0.0.1:5000
```

`create-admin` se ejecuta desde `backend/` porque la app importa `config.py` desde esa carpeta.

Variables de entorno opcionales: `SECRET_KEY`, `TICKET_SALT`, `SIMULATED_WEBHOOK_KEY`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `FLASK_DEBUG=1`. Si se cambia `TICKET_SALT`, los QR ya emitidos dejan de ser válidos.

Para liberar reservas vencidas a mano: `flask --app run expire-orders`.

### Tests

Usan una base aparte (`icoope_test`), así que no tocan la de desarrollo. Hace falta MariaDB corriendo con el usuario `root` sin contraseña.

```bash
cd backend
pytest
```

## 3. Product Backlog

Priorizado con MoSCoW para un MVP funcional en 2 meses.

| ID | Título del PBI | Story Points | Prioridad | Dependencias |
|---|---|---|---|---|
| PBI-01 | Entorno y modelo de datos MariaDB | 5 | Alta (Must) | Ninguna |
| PBI-02 | Autenticación JWT y control de roles (RBAC) | 8 | Alta (Must) | PBI-01 |
| PBI-03 | API del catálogo de tienda, eventos e inventario | 8 | Alta (Must) | PBI-01 |
| PBI-04 | API del foro de novedades y tablón de anuncios | 3 | Alta (Must) | PBI-02 |
| PBI-05 | Flujo transaccional de pagos (simulado) | 13 | Alta (Must) | PBI-03 |
| PBI-06 | Motor de generación de tickets QR | 5 | Alta (Must) | PBI-05 |
| PBI-07 | Endpoint validador de QR con consumo de estado real | 5 | Media (Should) | PBI-06 |
| PBI-08 | Dashboard de métricas financieras y auditoría contable | 8 | Media (Should) | PBI-05 |

## 4. Historias de usuario

### Épica: Compras e interacción del cliente

**HU1: Carrito mixto con reserva de stock**
Como padre de un alumno, quiero armar un carrito con la chomba del colegio y la entrada para la rifa anual y pagarlo todo junto, para optimizar mi tiempo y asegurar los insumos de mi hijo en una sola transacción digital.

Criterios de aceptación:
- Dado que el usuario añade múltiples productos al carrito, cuando hace clic en "Proceder al pago", entonces la API verifica el stock de cada ítem de manera aislada con bloqueo de filas (`SELECT ... FOR UPDATE`).
- Dado que hay stock suficiente, cuando se genera la orden en estado `PENDING`, entonces el sistema resta el stock durante un periodo de gracia de 15 minutos.
- Dado que el pago es rechazado o la reserva vence, entonces el backend libera el stock reservado y lo devuelve a su estado original.

**HU2: Acceso al foro de la cooperadora**
Como alumno o padre, quiero leer los comunicados oficiales de la cooperadora, para estar al tanto de los destinos de los fondos y las fechas de asambleas o ferias.

Criterios de aceptación:
- Dado que un usuario, anónimo o autenticado, entra al foro, entonces la API devuelve una lista paginada de publicaciones (las urgentes primero, luego por fecha descendente).
- Dado que un usuario con rol de cliente (`PADRE` o `ALUMNO`) intenta enviar un POST, PUT, PATCH o DELETE al foro (`/api/v1/foro`), entonces recibe `403 Forbidden`.

### Épica: Gestión y control de la cooperadora

**HU3: Publicación de novedades y anuncios oficiales**
Como miembro de la cooperadora, quiero redactar y publicar un anuncio en el foro, para difundir los resultados de la última recaudación o convocar a reuniones extraordinarias.

Criterios de aceptación:
- Dado que un usuario autenticado tiene entre sus roles `COOPERADORA` (o `ADMIN`, `DOCENTE`, `STAFF`), entonces puede consumir `POST /api/v1/foro`.
- Dado que el título o el contenido están vacíos, entonces la API responde `400 Bad Request` con el detalle del error.

**HU4: Administración del catálogo e inventario**
Como tesorero de la cooperadora, quiero dar de alta un producto físico o una entrada a un evento, para actualizar la oferta de la escuela según la temporada.

Criterios de aceptación:
- Dado que se registra un producto permanente, entonces `es_evento` se guarda como 0 y `fecha_evento` admite `NULL`.
- Dado que se registra un producto de tipo evento, entonces `es_evento` se guarda como 1 y `fecha_evento` es obligatoria (validada en la API y por un `CHECK` en la base).

### Épica: Operación de campo y validación antifraude

**HU5: Validación móvil de entradas**
Como colaborador del staff en la entrada del evento, quiero escanear el QR del ticket desde el celular, para verificar su autenticidad al instante y marcarlo como usado.

Criterios de aceptación:
- Dado que el colaborador escanea un QR, cuando el frontend envía el hash a `POST /api/v1/tickets/validar`, entonces el backend lo busca en `ticket_qr`.
- Dado que el ticket existe y `utilizado = 0`, entonces se actualiza de forma atómica a `utilizado = 1` con la hora exacta en `fecha_uso` y se responde `200 OK`.
- Dado que el ticket ya figura como usado, entonces se responde `409 Conflict` con la hora del primer uso para alertar de una posible clonación.