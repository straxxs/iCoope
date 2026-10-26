📑 DOCUMENTACIÓN TÉCNICA DE PROYECTO: ICope
1. DESCRIPCIÓN GENERAL DEL FUNCIONAMIENTO DEL SISTEMA
ICope es una plataforma web e-commerce y CMS centralizada que automatiza la operación financiera y comunicacional de la cooperadora escolar. El sistema opera bajo una arquitectura de API RESTful desacoplada del frontend, gestionando la persistencia de datos en un motor relacional MariaDB.
El sistema funciona como un ecosistema dinámico permanente basado en Roles de Acceso Estrictos (RBAC):
Módulo Administrativo (Miembros de la Cooperadora): Funciona como un panel de control centralizado (Backoffice). Permite la gestión del inventario de la tienda permanente (útiles, uniformes), la creación de eventos y rifas temporales con control de aforo/stock crítico, la moderación del foro de novedades institucionales y la visualización de analíticas de recaudación.
Módulo de Cliente (Padres, Alumnos y Docentes): Funciona como el portal público y transaccional. Los usuarios acceden de forma libre al foro de novedades para mantenerse informados. Mediante autenticación, acceden a la tienda virtual donde pueden consolidar en un solo "carrito de compras" productos físicos (ej. un cuaderno) y productos de eventos (ej. una rifa).
Módulo Operativo de Campo (Staff de Eventos): Sub-rol administrativo optimizado para dispositivos móviles. Utiliza la API nativa de la cámara para escanear y validar los códigos QR de los productos tipo evento en el momento de la acreditación o entrega de productos, previniendo fraudes por duplicación en tiempo real.
Mecanismo Transaccional y Criptográfico Corriente
Procesamiento de Pagos: Cuando un cliente confirma un carrito, el backend genera una Preferencia de Pago en la API de Mercado Pago. La orden se registra con estado PENDING e inmediatamente se reserva el stock temporalmente para evitar colisiones de compra distribuidas (problema del doble gasto).
Confirmación Asincrónica (Webhooks): La pasarela de pago notifica al backend mediante un Webhook. Si el pago es exitoso (APPROVED), la orden se consolida. Si la orden contiene ítems marcados como es_evento = TRUE, un servicio del backend genera un Hash criptográfico único (SHA-256 compuesto por id_usuario + id_detalle + salt_escuela). Este hash se inyecta en la base de datos de MariaDB y se renderiza en el frontend del cliente como un código QR seguro.

🗂️ PRODUCT BACKLOG (PILA DEL PRODUCTO)
El backlog está priorizado utilizando la metodología MoSCoW para garantizar un Producto Mínimo Viable (MVP) funcional en los 2 meses de desarrollo.
ID
Título del PBI
Estimación (Story Points)
Prioridad
Dependencias
PBI-01
Inicialización del Entorno y Modelo de Datos MariaDB
5
Alta (Must)
Ninguna
PBI-02
Sistema de Autenticación JWT y Control de Roles (RBAC)
8
Alta (Must)
PBI-01
PBI-03
API del Catálogo de Tienda, Eventos e Inventario
8
Alta (Must)
PBI-01
PBI-04
API del Foro de Novedades y Tablón de Anuncios
3
Alta (Must)
PBI-02
PBI-05
Integración Transaccional con Webhooks de Mercado Pago
13
Alta (Must)
PBI-03
PBI-06
Motor de Generación Criptográfica de Tickets QR
5
Alta (Must)
PBI-05
PBI-07
Endpoint Validador de QR con Consumo de Estado Real
5
Media (Should)
PBI-06
PBI-08
Dashboard de Métricas Financieras y Auditoría Contable
8
Media (Should)
PBI-05


👤 HISTORIAS DE USUARIO (USER STORIES)
Épica: Compras e Interacción del Cliente
HISTORIA DE USUARIO 1: Carrito de Compras Mixto con Reserva de Stock
Como Padre de un alumno,
Quiero armar un carrito de compras que contenga tanto la chomba del colegio como la entrada para la rifa anual y pagarlo todo junto,
Para optimizar mi tiempo y asegurar los insumos de mi hijo en una sola transacción digital.
Criterios de Aceptación:
Dado que el usuario añade múltiples productos al carrito, cuando hace clic en "Proceder al Pago", entonces la API de Flask debe verificar la disponibilidad de stock en MariaDB para cada ítem de manera aislada utilizando sentencias de bloqueo de filas (SELECT ... FOR UPDATE).
Dado que hay stock suficiente, cuando se genera la orden con estado PENDING, entonces el sistema debe restar temporalmente el stock físico del inventario general durante un periodo de gracia de 15 minutos.
Dado que la sesión de pago de Mercado Pago expira o es rechazada, cuando el webhook notifica la cancelación, entonces el backend de Flask debe liberar automáticamente el stock reservado devolviéndolo a su estado original en MariaDB.
HISTORIA DE USUARIO 2: Acceso e Interacción en el Foro de la Cooperadora
Como Alumno o Padre de la institución,
Quiero ingresar a la sección del foro de la plataforma para leer los comunicados oficiales de la cooperadora,
Para estar al tanto de los destinos de los fondos y las fechas de las próximas asambleas o ferias.
Criterios de Aceptación:
Dado que un usuario ingresa de manera anónima o autenticada a la ruta del foro, cuando el frontend solicita la información, entonces la API de Flask debe retornar una lista paginada de los posts ordenados cronológicamente de forma descendente.
Dado que un usuario con el rol CLIENTE intenta enviar una petición POST, PUT o DELETE al endpoint del foro (/api/v1/foro), cuando el middleware de Flask decodifique el token JWT, entonces debe retornar un código de estado HTTP 403 Forbidden.

Épica: Gestión y Control de la Cooperadora (Administración)
HISTORIA DE USUARIO 3: Publicación de Novedades y Anuncios Oficiales
Como Miembro de la Cooperadora Escolar,
Quiero redactar y publicar un nuevo anuncio en el foro de la plataforma,
Para difundir de forma masiva los resultados de la última recaudación o convocar a reuniones extraordinarias.
Criterios de Aceptación:
Dado que un usuario autenticado inicia sesión en el Backoffice, cuando el backend valida que su JWT contiene el parámetro rol == "cooperadora", entonces le permite consumir con éxito el endpoint POST /api/v1/foro.
Dado que el formulario de creación es enviado, cuando los campos titulo o contenido se encuentren vacíos, entonces la API debe interceptar la solicitud y responder con un código HTTP 400 Bad Request detallando los errores de validación.
HISTORIA DE USUARIO 4: Administración del Catálogo Unificado e Inventario
Como Tesorero de la Cooperadora,
Quiero dar de alta un nuevo producto físico (como un cuaderno) o un producto digital de evento (como una entrada a la fiesta de la primavera),
Para actualizar dinámicamente la oferta transaccional de la escuela según las necesidades de la temporada.
Criterios de Aceptación:
Dado que se registra un producto permanente (útiles/ropa), cuando se procesa la solicitud, entonces el campo binario es_evento debe persistirse como 0 (FALSE) en MariaDB y el campo fecha_evento debe admitir un valor nulo (NULL).
Dado que se registra un producto de tipo evento, cuando se envía la petición, entonces el campo es_evento debe persistirse como 1 (TRUE) y el campo fecha_evento pasa a ser estrictamente obligatorio mediante validación en el esquema de Flask.

Épica: Operación de Campo y Validación Antifraude
HISTORIA DE USUARIO 5: Validación Móvil de Entradas y Retiro de Productos
Como Colaborador del Staff de la cooperadora en la entrada del evento o buffet,
Quiero escanear el código QR del ticket de un cliente desde una interfaz web móvil,
Para verificar su autenticidad de forma instantánea y marcarlo como entregado en la base de datos local.
Criterios de Aceptación:
Dado que el colaborador escanea un código QR, cuando el frontend extrae el token y lo envía vía POST /api/v1/tickets/validar, entonces el backend debe buscar el hash en la tabla correspondiente de MariaDB.
Dado que el ticket existe y su columna utilizado es igual a 0 (FALSE), cuando el servidor procesa la lectura, entonces debe actualizar atómicamente la columna utilizado = 1 y registrar la marca de tiempo exacta en fecha_uso, respondiendo con un estatus HTTP 200 OK (Validación Exitosa).
Dado que el ticket ya registra un estado utilizado = 1, cuando la API es consultada, entonces debe retornar inmediatamente un código HTTP 409 Conflict, adjuntando la hora exacta del primer uso para alertar al staff sobre una clonación de ticket.

