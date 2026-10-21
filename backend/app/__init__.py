from datetime import date, datetime
from decimal import Decimal

from flask import Flask, jsonify
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS

from config import Config

from . import auth, catalog, community, db, errors, events, payments, users

from pathlib import Path
from flask import send_from_directory

class APIJSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(value):
        if isinstance(value, (datetime, date)):
            return value.isoformat()

        if isinstance(value, Decimal):
            return str(value)

        return DefaultJSONProvider.default(value)


def create_app(config_overrides=None):
    app = Flask(__name__, static_folder=None)
    app.json = APIJSONProvider(app)

    app.config.from_object(Config)

    if config_overrides:
        app.config.update(config_overrides)

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": app.config["CORS_ORIGINS"],
            }
        },
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Simulation-Key",
        ],
        methods=[
            "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
        ],
        supports_credentials=False,
    )

    db.init_app(app)
    errors.init_app(app)
    auth.init_app(app)

    app.register_blueprint(auth.bp)
    app.register_blueprint(catalog.bp)
    app.register_blueprint(events.bp)
    app.register_blueprint(community.bp)
    app.register_blueprint(payments.bp)
    app.register_blueprint(users.bp)

    @app.get("/api/health")
    def health():
        return jsonify(
            status="ok",
            service="icoope-api",
            pagos="simulados",
        )

    FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "login.html")

    @app.get("/<path:filename>")
    def frontend_files(filename):
        return send_from_directory(FRONTEND_DIR, filename)

    return app