import pymysql
from flask import current_app, jsonify
from werkzeug.exceptions import HTTPException


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def init_app(app):
    @app.errorhandler(APIError)
    def api_error(error):
        response = jsonify(error=error.message)
        response.status_code = error.status

        if error.status == 401:
            response.headers["WWW-Authenticate"] = "Bearer"

        return response

    @app.errorhandler(pymysql.err.IntegrityError)
    def integrity_error(error):
        current_app.logger.exception("Restricción de base de datos.")

        return jsonify(
            error="La operación viola una restricción de datos."
        ), 409

    @app.errorhandler(pymysql.MySQLError)
    def database_error(error):
        current_app.logger.exception("Error de MariaDB.")

        return jsonify(
            error="No se pudo completar la operación en MariaDB."
        ), 500

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code