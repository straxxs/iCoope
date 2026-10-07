from flask import Blueprint, Flask, jsonify
from flask_cors import CORS

from config import Config
from . import db


def create_health_blueprint() -> Blueprint:
    blueprint = Blueprint("health", __name__, url_prefix="/api")

    @blueprint.get("/health")
    def health():
        # Comprueba que el servidor responde, sin abrir una conexión SQL.
        return jsonify(
            status="ok",
            service="school-commerce-api",
        ), 200

    return blueprint


def validate_config(app: Flask) -> None:
    required_keys = (
        "SECRET_KEY",
        "DB_NAME",
        "DB_USER",
    )

    missing_keys = [
        key
        for key in required_keys
        if app.config.get(key) is None or app.config.get(key) == ""
    ]

    # Una cadena vacía es válida para ciertas instalaciones locales.
    # None significa que DB_PASSWORD no fue definida.
    if app.config.get("DB_PASSWORD") is None:
        missing_keys.append("DB_PASSWORD")

    if missing_keys:
        raise RuntimeError(
            "Faltan variables de configuración: "
            + ", ".join(missing_keys)
        )

    if not 1 <= app.config["DB_PORT"] <= 65535:
        raise RuntimeError("DB_PORT debe estar entre 1 y 65535.")

def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)

    app.config.from_object(Config)

    # Permite ajustar la configuración en pruebas sin cambiar el entorno.
    if config_overrides is not None:
        app.config.update(config_overrides)

    validate_config(app)

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": app.config["CORS_ORIGINS"],
            }
        },
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        supports_credentials=False,
    )

    db.init_app(app)

    app.register_blueprint(create_health_blueprint())

    # Registrar aquí los blueprints de los futuros módulos:
    # from .modules.products.routes import products_bp
    # app.register_blueprint(products_bp, url_prefix="/api/products")

    return app