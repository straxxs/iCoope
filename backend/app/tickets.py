import hashlib
import hmac
import re

from flask import Blueprint, current_app, g, jsonify

from .auth import jwt_required, roles_required
from .db import fetch_all, fetch_one, transaction
from .errors import APIError
from .utils import body, require_row


bp = Blueprint("tickets", __name__, url_prefix="/api")

STAFF_ROLES = ("ADMIN", "COOPERADORA", "STAFF")
PAID_STATES = ("APPROVED", "READY", "DELIVERED")
HASH_RE = re.compile(r"[0-9a-f]{64}")


def make_hash(user_id, detail_id):
    """SHA-256 (HMAC) sobre id_usuario + id_detalle con la sal de la escuela."""
    key = current_app.config["TICKET_SALT"].encode("utf-8")
    message = f"{user_id}:{detail_id}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def generate_tickets(cursor, order):
    """Crea un ticket por cada línea del pedido que sea de un evento.

    Se llama dentro de la transacción que aprueba el pago. Es idempotente
    gracias a INSERT IGNORE sobre id_detalle (UNIQUE).
    """
    cursor.execute(
        """
        SELECT d.id_detalle
        FROM detalle_pedido d
        JOIN variante_producto v ON v.id_variante = d.id_variante
        JOIN producto p ON p.id_producto = v.id_producto
        WHERE d.id_pedido = %s AND p.es_evento = TRUE
        ORDER BY d.id_detalle
        """,
        (order["id_pedido"],),
    )
    details = cursor.fetchall()

    for row in details:
        cursor.execute(
            "INSERT IGNORE INTO ticket_qr (id_detalle, hash_qr) "
            "VALUES (%s, %s)",
            (
                row["id_detalle"],
                make_hash(order["id_usuario"], row["id_detalle"]),
            ),
        )

    return len(details)


@bp.get("/orders/<int:order_id>/tickets")
@jwt_required
def order_tickets(order_id):
    order = require_row(
        fetch_one(
            "SELECT id_pedido, id_usuario, estado FROM pedido "
            "WHERE id_pedido = %s",
            (order_id,),
        ),
        "Pedido no encontrado.",
    )
    user = g.current_user

    if (
        order["id_usuario"] != user["id_usuario"]
        and not set(STAFF_ROLES).intersection(user["roles"])
    ):
        raise APIError("No puedes acceder a este pedido.", 403)

    if order["estado"] not in PAID_STATES:
        return jsonify(entradas=[])

    rows = fetch_all(
        """
        SELECT t.id_ticket, t.hash_qr, t.utilizado, t.fecha_uso,
               d.cantidad, p.nombre AS producto, v.nombre AS variante,
               p.fecha_evento
        FROM ticket_qr t
        JOIN detalle_pedido d ON d.id_detalle = t.id_detalle
        JOIN variante_producto v ON v.id_variante = d.id_variante
        JOIN producto p ON p.id_producto = v.id_producto
        WHERE d.id_pedido = %s
        ORDER BY t.id_ticket
        """,
        (order_id,),
    )

    for row in rows:
        row["utilizado"] = bool(row["utilizado"])

    return jsonify(entradas=rows)


@bp.post("/v1/tickets/validar")
@bp.post("/tickets/validate")
@roles_required(*STAFF_ROLES)
def validate_ticket():
    data = body({"hash", "token"})
    value = data.get("hash") or data.get("token")

    if not isinstance(value, str):
        raise APIError("Falta el código del ticket.")

    value = value.strip().lower()

    if not HASH_RE.fullmatch(value):
        raise APIError("El código QR no tiene un formato válido.")

    with transaction() as cursor:
        # Se bloquea solo la fila del ticket: dos escaneos simultáneos
        # se serializan y el segundo ve utilizado = 1.
        cursor.execute(
            "SELECT id_ticket, id_detalle, utilizado, fecha_uso "
            "FROM ticket_qr WHERE hash_qr = %s FOR UPDATE",
            (value,),
        )
        ticket = cursor.fetchone()

        if ticket is None:
            raise APIError("Ticket no encontrado.", 404)

        if ticket["utilizado"]:
            when = ticket["fecha_uso"]
            raise APIError(
                "Ticket ya utilizado el "
                f"{when:%d/%m/%Y a las %H:%M:%S}. Posible clonación.",
                409,
                extra={"fecha_uso": when},
            )

        cursor.execute(
            """
            SELECT o.estado, d.cantidad, p.nombre AS producto,
                   v.nombre AS variante, u.nombre, u.apellido
            FROM detalle_pedido d
            JOIN pedido o ON o.id_pedido = d.id_pedido
            JOIN usuario u ON u.id_usuario = o.id_usuario
            JOIN variante_producto v ON v.id_variante = d.id_variante
            JOIN producto p ON p.id_producto = v.id_producto
            WHERE d.id_detalle = %s
            """,
            (ticket["id_detalle"],),
        )
        info = cursor.fetchone()

        if info is None or info["estado"] not in PAID_STATES:
            raise APIError("El pedido de este ticket no está pagado.", 409)

        cursor.execute(
            "UPDATE ticket_qr SET utilizado = TRUE, fecha_uso = NOW() "
            "WHERE id_ticket = %s AND utilizado = FALSE",
            (ticket["id_ticket"],),
        )
        cursor.execute(
            "SELECT fecha_uso FROM ticket_qr WHERE id_ticket = %s",
            (ticket["id_ticket"],),
        )
        used_at = cursor.fetchone()["fecha_uso"]

    return jsonify(
        valido=True,
        ticket={
            "id_ticket": ticket["id_ticket"],
            "producto": info["producto"],
            "variante": info["variante"],
            "cantidad": info["cantidad"],
            "titular": f"{info['nombre']} {info['apellido']}",
            "fecha_uso": used_at,
        },
    )