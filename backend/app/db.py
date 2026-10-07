from contextlib import contextmanager
from typing import Iterator

import pymysql
from flask import Flask, current_app, g
from pymysql.connections import Connection
from pymysql.cursors import DictCursor


def get_db() -> Connection:
    """Obtiene la conexión asociada al contexto actual de Flask."""
    if "db_connection" not in g:
        config = current_app.config

        connection_options = {
            "host": config["DB_HOST"],
            "port": config["DB_PORT"],
            "user": config["DB_USER"],
            "password": config["DB_PASSWORD"],
            "database": config["DB_NAME"],
            "charset": "utf8mb4",
            "cursorclass": DictCursor,
            "autocommit": False,
            "connect_timeout": config["DB_CONNECT_TIMEOUT"],
            "read_timeout": config["DB_READ_TIMEOUT"],
            "write_timeout": config["DB_WRITE_TIMEOUT"],
        }

        if config.get("DB_SSL_CA"):
            connection_options.update(
                ssl_ca=config["DB_SSL_CA"],
                ssl_verify_cert=True,
                ssl_verify_identity=True,
            )

        g.db_connection = pymysql.connect(**connection_options)

    return g.db_connection


@contextmanager
def transaction() -> Iterator[Connection]:
    """
    Confirma los cambios al completar el bloque.

    Si ocurre un error, revierte la transacción y propaga la excepción.
    No permite transacciones anidadas.
    """
    if g.get("db_transaction_active", False):
        raise RuntimeError("No se permiten transacciones anidadas.")

    connection = get_db()
    g.db_transaction_active = True

    try:
        yield connection
        connection.commit()
    except BaseException:
        try:
            connection.rollback()
        except pymysql.MySQLError:
            current_app.logger.exception(
                "No se pudo revertir la transacción."
            )
        raise
    finally:
        g.pop("db_transaction_active", None)


def close_db(exception: BaseException | None = None) -> None:
    """Libera la conexión al finalizar el contexto de aplicación."""
    connection = g.pop("db_connection", None)
    g.pop("db_transaction_active", None)

    if connection is None:
        return

    try:
        # Evita dejar cambios sin confirmar, incluso si no hubo excepción.
        connection.rollback()
    except pymysql.MySQLError:
        current_app.logger.exception(
            "Error al revertir operaciones pendientes durante el cierre."
        )
    finally:
        try:
            connection.close()
        except pymysql.MySQLError:
            current_app.logger.exception(
                "Error al cerrar la conexión a la base de datos."
            )


def init_app(app: Flask) -> None:
    """Registra la limpieza automática de conexiones."""
    app.teardown_appcontext(close_db)