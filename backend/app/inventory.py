import click
from flask import Blueprint, jsonify, request

from .auth import roles_required
from .db import fetch_all, fetch_one, transaction
from .errors import APIError
from .payments import restore_stock
from .utils import integer


bp = Blueprint("inventory", __name__, url_prefix="/api/inventory")

MANAGERS = ("ADMIN", "COOPERADORA", "STAFF")


def release_expired_orders(limit=50):
    """Cancela los pedidos PENDING cuya reserva de stock venció y
    devuelve el stock. Devuelve la lista de ids liberados.

    No toca pedidos con una transferencia pendiente de verificación,
    porque la familia ya reportó el pago y no debe perder la reserva
    mientras la cooperadora lo revisa.
    """
    expired = fetch_all(
        """
        SELECT p.id_pedido
        FROM pedido p
        WHERE p.estado = 'PENDING'
          AND p.fecha_vencimiento_reserva IS NOT NULL
          AND p.fecha_vencimiento_reserva < NOW()
        ORDER BY p.id_pedido
        LIMIT %s
        """,
        (limit,),
    )

    released = []

    for row in expired:
        order_id = row["id_pedido"]

        with transaction() as cursor:
            # Se revalida todo después de bloquear el pedido, porque
            # mientras tanto pudo pagarse o cancelarse.
            cursor.execute(
                """
                SELECT id_pedido FROM pedido
                WHERE id_pedido = %s
                  AND estado = 'PENDING'
                  AND fecha_vencimiento_reserva < NOW()
                FOR UPDATE
                """,
                (order_id,),
            )

            if cursor.fetchone() is None:
                continue

            cursor.execute(
                """
                SELECT 1 FROM pago
                WHERE id_pedido = %s
                  AND metodo = 'TRANSFERENCIA'
                  AND estado = 'PENDING'
                LIMIT 1
                """,
                (order_id,),
            )

            if cursor.fetchone() is not None:
                continue

            restore_stock(cursor, order_id)

            cursor.execute(
                "UPDATE pedido SET estado = 'CANCELLED' "
                "WHERE id_pedido = %s",
                (order_id,),
            )
            cursor.execute(
                "UPDATE pago SET estado = 'CANCELLED' "
                "WHERE id_pedido = %s AND estado = 'PENDING'",
                (order_id,),
            )

        released.append(order_id)

    return released


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
        click.echo(f"Pedidos liberados: {len(released)}")