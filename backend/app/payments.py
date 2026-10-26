import secrets
from decimal import Decimal
from uuid import uuid4

from flask import Blueprint, current_app, g, jsonify, request

from .auth import is_admin, jwt_required, roles_required
from .db import fetch_all, fetch_one, transaction, get_db
from .errors import APIError
from .utils import body, integer, pagination, require_row


bp = Blueprint("payments", __name__, url_prefix="/api")


MANAGER_ROLES = {"ADMIN", "COOPERADORA", "STAFF"}

def ensure_simulation():
    if not current_app.config["SIMULATED_PAYMENTS_ENABLED"]:
        raise APIError("Los pagos simulados están deshabilitados.", 403)


def is_manager():
    return bool(MANAGER_ROLES.intersection(g.current_user["roles"]))


def check_order_access(order, allow_staff=False):
    if order["id_usuario"] == g.current_user["id_usuario"]:
        return

    if is_admin() or (allow_staff and is_manager()):
        return

    raise APIError("No puedes acceder a este pedido.", 403)


def order_detail(order_id):
    order = require_row(
        fetch_one(
            "SELECT * FROM pedido WHERE id_pedido = %s",
            (order_id,),
        ),
        "Pedido no encontrado.",
    )
    check_order_access(order, allow_staff=True)

    details = fetch_all(
        """
        SELECT d.*, v.nombre AS variante, p.nombre AS producto
        FROM detalle_pedido d
        JOIN variante_producto v ON v.id_variante = d.id_variante
        JOIN producto p ON p.id_producto = v.id_producto
        WHERE d.id_pedido = %s
        ORDER BY d.id_detalle
        """,
        (order_id,),
    )

    order["detalles"] = details
    order["total"] = sum(
        (
            row["precio_unitario"] * row["cantidad"]
            for row in details
        ),
        Decimal("0.00"),
    )
    order["pagos"] = fetch_all(
        "SELECT * FROM pago WHERE id_pedido = %s ORDER BY id_pago",
        (order_id,),
    )

    return order


def restore_stock(cursor, order_id):
    cursor.execute(
        """
        SELECT id_variante, SUM(cantidad) AS cantidad
        FROM detalle_pedido
        WHERE id_pedido = %s
        GROUP BY id_variante
        ORDER BY id_variante
        """,
        (order_id,),
    )
    details = cursor.fetchall()

    for detail in details:
        cursor.execute(
            "SELECT stock FROM variante_producto "
            "WHERE id_variante = %s FOR UPDATE",
            (detail["id_variante"],),
        )
        variant = require_row(cursor.fetchone())

        stock = variant["stock"] + int(detail["cantidad"])

        if stock > 2147483647:
            raise APIError(
                "No se puede devolver el stock: supera el máximo.",
                409,
            )

        cursor.execute(
            "UPDATE variante_producto SET stock = %s "
            "WHERE id_variante = %s",
            (stock, detail["id_variante"]),
        )
EXPIRY_PREFIXES = ("/api/products", "/api/orders", "/api/payments")


def release_expired_orders(limit=50):
    """Cancela pedidos PENDING vencidos y devuelve su stock."""
    expired = fetch_all(
        """
        SELECT id_pedido FROM pedido
        WHERE estado = 'PENDING'
          AND fecha_vencimiento_reserva IS NOT NULL
          AND fecha_vencimiento_reserva <= NOW()
        ORDER BY id_pedido
        LIMIT %s
        """,
        (limit,),
    )

    if not expired:
        get_db().commit()  # cierra el snapshot de la lectura
        return 0

    released = 0

    # Un pedido por transacción: evita bloqueos cruzados.
    for row in expired:
        with transaction() as cursor:
            cursor.execute(
                """
                SELECT id_pedido FROM pedido
                WHERE id_pedido = %s
                  AND estado = 'PENDING'
                  AND fecha_vencimiento_reserva <= NOW()
                FOR UPDATE
                """,
                (row["id_pedido"],),
            )

            if cursor.fetchone() is None:
                continue  # otro proceso ya lo resolvió

            restore_stock(cursor, row["id_pedido"])

            cursor.execute(
                "UPDATE pedido SET estado = 'CANCELLED' "
                "WHERE id_pedido = %s",
                (row["id_pedido"],),
            )
            cursor.execute(
                "UPDATE pago SET estado = 'CANCELLED' "
                "WHERE id_pedido = %s AND estado = 'PENDING'",
                (row["id_pedido"],),
            )
            released += 1

    return released


@bp.before_app_request
def release_expired_before_request():
    if request.method == "OPTIONS":
        return

    if not request.path.startswith(EXPIRY_PREFIXES):
        return

    try:
        release_expired_orders()
    except Exception:
        current_app.logger.exception(
            "No se pudieron liberar las reservas vencidas."
        )


@bp.post("/orders/release-expired")
@roles_required("ADMIN", "COOPERADORA")
def release_expired_endpoint():
    return jsonify(liberados=release_expired_orders(limit=500))

@bp.post("/orders")
@jwt_required
def create_order():
    data = body({"items"})
    items = data.get("items")

    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise APIError("items debe contener entre 1 y 100 elementos.")

    quantities = {}

    for item in items:
        if (
            not isinstance(item, dict)
            or set(item) != {"id_variante", "cantidad"}
        ):
            raise APIError(
                "Cada item debe tener id_variante y cantidad."
            )

        variant_id = integer(item["id_variante"], "id_variante")
        quantity = integer(
            item["cantidad"],
            "cantidad",
            maximum=1000,
        )

        quantities[variant_id] = quantities.get(variant_id, 0) + quantity

        if quantities[variant_id] > 1000:
            raise APIError(
                "Máximo 1000 unidades por variante en cada pedido."
            )

    with transaction() as cursor:
        # Bloqueo en orden estable para reducir conflictos concurrentes.
        selected = []
        total = Decimal("0.00")

        for variant_id in sorted(quantities):
            cursor.execute(
                """
                SELECT v.id_variante, v.stock, p.precio, p.activo
                FROM variante_producto v
                JOIN producto p ON p.id_producto = v.id_producto
                WHERE v.id_variante = %s
                FOR UPDATE
                """,
                (variant_id,),
            )
            variant = require_row(
                cursor.fetchone(),
                "Una variante no existe.",
            )

            quantity = quantities[variant_id]

            if not variant["activo"]:
                raise APIError("Uno de los productos está inactivo.", 409)

            if variant["stock"] < quantity:
                raise APIError(
                    f"Stock insuficiente para la variante {variant_id}.",
                    409,
                )

            total += variant["precio"] * quantity
            selected.append((variant_id, quantity, variant["precio"]))

        if total > Decimal("99999999.99"):
            raise APIError("El pedido supera el importe permitido.")

        cursor.execute(
            """
            INSERT INTO pedido (id_usuario, fecha_vencimiento_reserva)
            VALUES (%s, NOW() + INTERVAL %s MINUTE)
            """,
            (
                g.current_user["id_usuario"],
                current_app.config["RESERVATION_MINUTES"],
            ),
        )
        order_id = cursor.lastrowid

        for variant_id, quantity, price in selected:
            cursor.execute(
                """
                INSERT INTO detalle_pedido (
                    id_pedido, id_variante, cantidad, precio_unitario
                )
                VALUES (%s, %s, %s, %s)
                """,
                (order_id, variant_id, quantity, price),
            )

            cursor.execute(
                "UPDATE variante_producto SET stock = stock - %s "
                "WHERE id_variante = %s",
                (quantity, variant_id),
            )

    return jsonify(pedido=order_detail(order_id)), 201


@bp.get("/orders")
@jwt_required
def list_orders():
    page, limit, offset = pagination()
    conditions, params = [], []

    if request.args.get("todos") == "true":
        if not is_manager():
            raise APIError("No tienes permisos.", 403)
    else:
        conditions.append("id_usuario = %s")
        params.append(g.current_user["id_usuario"])

    estado = request.args.get("estado")

    if estado:
        if estado not in {
            "PENDING", "APPROVED", "REJECTED",
            "CANCELLED", "READY", "DELIVERED",
        }:
            raise APIError("Estado de pedido no válido.")

        conditions.append("estado = %s")
        params.append(estado)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    return jsonify(
        pedidos=fetch_all(
            f"""
            SELECT * FROM pedido {where}
            ORDER BY id_pedido DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params + [limit, offset]),
        ),
        page=page,
        per_page=limit,
    )

@bp.get("/orders/<int:order_id>")
@jwt_required
def get_order(order_id):
    return jsonify(pedido=order_detail(order_id))


@bp.post("/orders/<int:order_id>/cancel")
@jwt_required
def cancel_order(order_id):
    with transaction() as cursor:
        cursor.execute(
            "SELECT * FROM pedido WHERE id_pedido = %s FOR UPDATE",
            (order_id,),
        )
        order = require_row(cursor.fetchone())
        check_order_access(order)

        if order["estado"] == "CANCELLED":
            return jsonify(message="El pedido ya estaba cancelado.")

        if order["estado"] != "PENDING":
            raise APIError(
                "Solo se pueden cancelar pedidos pendientes.",
                409,
            )

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

    return jsonify(pedido=order_detail(order_id))


@bp.post("/orders/<int:order_id>/payments")
@jwt_required
def create_payment(order_id):
    ensure_simulation()
    data = body({"metodo"})
    method = data.get("metodo", "MERCADO_PAGO")

    if method not in {"MERCADO_PAGO", "TRANSFERENCIA"}:
        raise APIError("Método de pago no permitido.")

    with transaction() as cursor:
        cursor.execute(
            "SELECT * FROM pedido WHERE id_pedido = %s FOR UPDATE",
            (order_id,),
        )
        order = require_row(cursor.fetchone())
        check_order_access(order)

        if order["estado"] != "PENDING":
            raise APIError("El pedido no está pendiente.", 409)

        cursor.execute(
            "SELECT id_pago FROM pago WHERE id_pedido = %s LIMIT 1",
            (order_id,),
        )

        if cursor.fetchone() is not None:
            raise APIError(
                "Este pedido ya tiene un intento de pago.",
                409,
            )

        cursor.execute(
            """
            SELECT COALESCE(
                SUM(cantidad * precio_unitario), 0
            ) AS total
            FROM detalle_pedido
            WHERE id_pedido = %s
            """,
            (order_id,),
        )
        amount = cursor.fetchone()["total"]

        cursor.execute(
            """
            INSERT INTO pago (
                id_pedido, metodo, monto, referencia
            )
            VALUES (%s, %s, %s, %s)
            """,
            (order_id, method, amount, f"SIM-{uuid4().hex}"),
        )
        payment_id = cursor.lastrowid

    return jsonify(
        simulado=True,
        pago=fetch_one(
            "SELECT * FROM pago WHERE id_pago = %s",
            (payment_id,),
        ),
    ), 201


def process_payment_result(payment_id, result, check_owner=False):
    if result not in {"APPROVED", "REJECTED"}:
        raise APIError("El estado debe ser APPROVED o REJECTED.")

    initial = require_row(
        fetch_one(
            "SELECT id_pedido FROM pago WHERE id_pago = %s",
            (payment_id,),
        ),
        "Pago no encontrado.",
    )

    with transaction() as cursor:
        # Todas las operaciones del pago bloquean primero el pedido.
        cursor.execute(
            "SELECT * FROM pedido WHERE id_pedido = %s FOR UPDATE",
            (initial["id_pedido"],),
        )
        order = require_row(cursor.fetchone())

        if check_owner:
            check_order_access(order)

        cursor.execute(
            "SELECT * FROM pago WHERE id_pago = %s FOR UPDATE",
            (payment_id,),
        )
        payment = require_row(cursor.fetchone())

        # Una notificación repetida no vuelve a modificar el stock.
        if payment["estado"] == result:
            return {
                "id_pago": payment_id,
                "estado": result,
                "duplicado": True,
            }

        if payment["estado"] != "PENDING":
            raise APIError(
                "El pago ya tiene otro estado definitivo.",
                409,
            )

        if order["estado"] != "PENDING":
            raise APIError("El pedido ya no está pendiente.", 409)

        if result == "REJECTED":
            restore_stock(cursor, order["id_pedido"])

        cursor.execute(
            """
            UPDATE pago
            SET estado = %s,
                fecha_pago = CASE
                    WHEN %s = 'APPROVED' THEN NOW()
                    ELSE NULL
                END
            WHERE id_pago = %s
            """,
            (result, result, payment_id),
        )

        cursor.execute(
            "UPDATE pedido SET estado = %s WHERE id_pedido = %s",
            (result, order["id_pedido"]),
        )

    return {
        "id_pago": payment_id,
        "estado": result,
        "duplicado": False,
    }


@bp.post("/payments/<int:payment_id>/simulate")
@jwt_required
def simulate_payment(payment_id):
    ensure_simulation()
    data = body({"estado"})

    result = process_payment_result(
        payment_id,
        data.get("estado"),
        check_owner=True,
    )

    return jsonify(simulado=True, **result)


@bp.post("/payments/webhooks/simulated")
def simulated_webhook():
    ensure_simulation()

    received_key = request.headers.get("X-Simulation-Key", "")
    expected_key = current_app.config["SIMULATED_WEBHOOK_KEY"]

    if not secrets.compare_digest(
        received_key.encode("utf-8"),
        expected_key.encode("utf-8"),
    ):
        raise APIError("Clave de simulación incorrecta.", 401)

    data = body({"id_pago", "estado"})
    payment_id = integer(data.get("id_pago"), "id_pago")

    result = process_payment_result(
        payment_id,
        data.get("estado"),
    )

    return jsonify(simulado=True, **result)


@bp.patch("/orders/<int:order_id>/status")
@roles_required("ADMIN", "COOPERADORA", "STAFF")
def update_order_status(order_id):
    data = body({"estado"})
    target = data.get("estado")

    if target not in {"READY", "DELIVERED"}:
        raise APIError("El estado debe ser READY o DELIVERED.")

    previous = {
        "READY": "APPROVED",
        "DELIVERED": "READY",
    }

    with transaction() as cursor:
        cursor.execute(
            "SELECT * FROM pedido WHERE id_pedido = %s FOR UPDATE",
            (order_id,),
        )
        order = require_row(cursor.fetchone())

        if order["estado"] != previous[target]:
            raise APIError(
                f"Para pasar a {target}, el pedido debe estar "
                f"en {previous[target]}.",
                409,
            )

        cursor.execute(
            "UPDATE pedido SET estado = %s WHERE id_pedido = %s",
            (target, order_id),
        )

    return jsonify(id_pedido=order_id, estado=target)