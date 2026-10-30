import click
from flask import Blueprint, jsonify, request

from .auth import roles_required
from .db import fetch_all, fetch_one
from .errors import APIError
from .payments import release_expired_orders
from .utils import integer


bp = Blueprint("inventory", __name__, url_prefix="/api/inventory")

MANAGERS = ("ADMIN", "COOPERADORA", "STAFF")


@bp.get("/low-stock")
@roles_required(*MANAGERS)
def low_stock():
    try:
        threshold = int(request.args.get("umbral", "5"))
    except ValueError:
        raise APIError("umbral debe ser un entero.")

    threshold = integer(threshold, "umbral", minimum=0, maximum=100000)

    rows = fetch_all(
        """
        SELECT v.id_variante, v.nombre AS variante, v.stock,
               p.id_producto, p.nombre AS producto, p.es_evento,
               c.nombre AS categoria
        FROM variante_producto v
        JOIN producto p ON p.id_producto = v.id_producto
        JOIN categoria c ON c.id_categoria = p.id_categoria
        WHERE p.activo = TRUE AND v.stock <= %s
        ORDER BY v.stock, p.nombre, v.nombre
        LIMIT 200
        """,
        (threshold,),
    )

    for row in rows:
        row["es_evento"] = bool(row["es_evento"])

    return jsonify(umbral=threshold, alertas=rows)


@bp.get("/summary")
@roles_required(*MANAGERS)
def summary():
    row = fetch_one(
        """
        SELECT COUNT(*) AS variantes,
               CAST(COALESCE(SUM(v.stock), 0) AS SIGNED) AS unidades,
               CAST(COALESCE(SUM(v.stock = 0), 0) AS SIGNED) AS agotadas
        FROM variante_producto v
        JOIN producto p ON p.id_producto = v.id_producto
        WHERE p.activo = TRUE
        """
    )

    return jsonify(resumen=row)


@bp.post("/expire-orders")
@roles_required("ADMIN", "COOPERADORA")
def expire_orders_endpoint():
    return jsonify(liberados=release_expired_orders(limit=500))


def init_app(app):
    @app.cli.command("expire-orders")
    def expire_orders_command():
        released = release_expired_orders(limit=500)
        click.echo(f"Pedidos liberados: {released}")