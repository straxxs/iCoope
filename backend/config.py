class Config:
    # Exclusivamente para la demo local.
    SECRET_KEY = "icoope-demo-local-clave-jwt-2026"

    DB_HOST = "127.0.0.1"
    DB_PORT = 3306
    DB_NAME = "icoope"
    DB_USER = "root"
    DB_PASSWORD = ""

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
    PUBLIC_REGISTRATION_ROLE = "ALUMNO"

    # No hay integración real con Mercado Pago.
    SIMULATED_PAYMENTS_ENABLED = True
    SIMULATED_WEBHOOK_KEY = "icoope-webhook-demo-local"

    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    
    STOCK_RESERVATION_MINUTES = 15
    RESERVATION_MINUTES = 15