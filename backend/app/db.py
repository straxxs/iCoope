from contextlib import contextmanager

import pymysql
from flask import current_app, g
from pymysql.cursors import DictCursor


def get_db():
    if "db" not in g:
        g.db = pymysql.connect(
            host=current_app.config["DB_HOST"],
            port=current_app.config["DB_PORT"],
            user=current_app.config["DB_USER"],
            password=current_app.config["DB_PASSWORD"],
            database=current_app.config["DB_NAME"],
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=current_app.config["DB_CONNECT_TIMEOUT"],
            read_timeout=current_app.config["DB_READ_TIMEOUT"],
            write_timeout=current_app.config["DB_WRITE_TIMEOUT"],
        )

    return g.db


def fetch_one(sql, params=()):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()


def fetch_all(sql, params=()):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


@contextmanager
def transaction():
    if g.get("transaction_active", False):
        raise RuntimeError("No se permiten transacciones anidadas.")

    connection = get_db()
    g.transaction_active = True

    try:
        with connection.cursor() as cursor:
            yield cursor

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
        g.pop("transaction_active", None)


def close_db(exception=None):
    connection = g.pop("db", None)
    g.pop("transaction_active", None)

    if connection is None:
        return

    try:
        connection.rollback()
    except pymysql.MySQLError:
        current_app.logger.exception(
            "Error al revertir operaciones pendientes."
        )
    finally:
        try:
            connection.close()
        except pymysql.MySQLError:
            current_app.logger.exception(
                "Error al cerrar la conexión."
            )


def init_app(app):
    app.teardown_appcontext(close_db)