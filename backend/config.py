import os


class Config:
    # Los valores por defecto son solo para la demo local.
    # En cualquier otro entorno se definen con variables de entorno.
    SECRET_KEY = os.environ.get("SECRET_KEY", "icoope-demo-local-clave-jwt-2026")

    DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_NAME = os.environ.get("DB_NAME", "icoope")
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

    DB_CONNECT_TIMEOUT = 10
    DB_READ_TIMEOUT = 30
    DB_WRITE_TIMEOUT = 30

    CORS_ORIGINS = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    MAX_CONTENT_LENGTH = 2 * 1024 * 1024

    JWT_ACCESS_TOKEN_MINUTES = 60
    JWT_ISSUER = "icoope-api"
    JWT_AUDIENCE = "icoope-frontend"

    PUBLIC_REGISTRATION_ENABLED = True
    PUBLIC_REGISTRATION_ROLE = "ALUMNO"  # rol por defecto si no se elige otro

    # No hay integración real con Mercado Pago: los pagos son simulados.
    SIMULATED_PAYMENTS_ENABLED = True
    SIMULATED_WEBHOOK_KEY = os.environ.get(
        "SIMULATED_WEBHOOK_KEY", "icoope-webhook-demo-local"
    )

    # Minutos que se reserva el stock de un pedido pendiente.
    RESERVATION_MINUTES = 15

    # Sal para los hashes de los tickets QR.
    # Si se cambia, los QR ya emitidos dejan de coincidir.
    TICKET_SALT = os.environ.get(
        "TICKET_SALT", "icoope-ticket-salt-demo-local-2026"
    )

    # Límite de intentos (Flask-Limiter).
    RATELIMIT_STORAGE_URI = "memory://"