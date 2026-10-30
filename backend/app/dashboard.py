import csv
import io

from flask import Blueprint, Response, jsonify, request

from .auth import roles_required
from .db import fetch_all, fetch_one
from .utils import date_time


bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")

FINANCE = ("ADMIN", "COOPERADORA")


def approved_filter():
    """Pagos aprobados; 'desde' inclusivo y 'hasta' exclusivo."""
    conditions = ["pg.estado = 'APPROVED'"]
    params = []

    since = request.args.get("desde")
    if since:
        conditions.append("pg.fecha_pago >= %s")
        params.append(date_time(since, "desde"))

    until = request.args.get("hasta")
    if until:
        conditions.append("pg.fecha_pago < %s")
        params.append(date_time(until, "hasta"))

    return " AND ".join(conditions), tuple(params)


@bp.get("/summary")
@roles_required(*FINANCE)
def summary():
    where, params = approved_filter()

    totals = fetch_one(
        f"""
        SELECT COALESCE(SUM(pg.monto), 0) AS total, COUNT(*) AS pagos
        FROM pago pg WHERE {where}
        """,
        params,
    )

    by_day = fetch_all(
        f"""
        SELECT DATE(pg.fecha_pago) AS dia,
               SUM(pg.monto) AS total, COUNT(*) AS pagos
        FROM pago pg WHERE {where}
        GROUP BY DATE(pg.fecha_pago)
        ORDER BY dia
        """,
        params,
    )

    by_category = fetch_all(
        f"""
        SELECT c.nombre AS categoria,
               CAST(SUM(d.cantidad) AS SIGNED) AS unidades,
               SUM(d.cantidad * d.precio_unitario) AS total
        FROM pago pg
        JOIN detalle_pedido d ON d.id_pedido = pg.id_pedido
        JOIN variante_producto v ON v.id_variante = d.id_variante
        JOIN producto p ON p.id_producto = v.id_producto
        JOIN categoria c ON c.id_categoria = p.id_categoria
        WHERE {where}
        GROUP BY c.id_categoria, c.nombre
        ORDER BY total DESC
        """,
        params,
    )

    top_products = fetch_all(
        f"""
        SELECT p.nombre AS producto, p.es_evento,
               CAST(SUM(d.cantidad) AS SIGNED) AS unidades,
               SUM(d.cantidad * d.precio_unitario) AS total
        FROM pago pg
        JOIN detalle_pedido d ON d.id_pedido = pg.id_pedido
        JOIN variante_producto v ON v.id_variante = d.id_variante
        JOIN producto p ON p.id_producto = v.id_producto
        WHERE {where}
        GROUP BY p.id_producto, p.nombre, p.es_evento
        ORDER BY unidades DESC
        LIMIT 10
        """,
        params,
    )

    for row in top_products:
        row["es_evento"] = bool(row["es_evento"])

    states = fetch_all(
        "SELECT estado, COUNT(*) AS total FROM pedido "
        "GROUP BY estado ORDER BY estado"
    )

    tickets = fetch_one(
        """
        SELECT COUNT(*) AS emitidas,
               CAST(COALESCE(SUM(utilizado), 0) AS SIGNED) AS usadas
        FROM ticket_qr
        """
    )

    return jsonify(
        recaudacion=totals["total"],
        pagos_aprobados=totals["pagos"],
        por_dia=by_day,
        por_categoria=by_category,
        top_productos=top_products,
        pedidos_por_estado=states,
        entradas=tickets,
        pagos_simulados=True,
    )


def safe_cell(value):
    """Evita inyección de fórmulas al abrir el CSV en Excel."""
    cell = "" if value is None else str(value)
    return "'" + cell if cell[:1] in ("=", "+", "-", "@") else cell


@bp.get("/export.csv")
@roles_required(*FINANCE)
def export_csv():
    where, params = approved_filter()

    rows = fetch_all(
        f"""
        SELECT pg.id_pago, pg.id_pedido, u.email, pg.metodo, pg.monto,
               pg.referencia, pg.fecha_pago
        FROM pago pg
        JOIN pedido o ON o.id_pedido = pg.id_pedido
        JOIN usuario u ON u.id_usuario = o.id_usuario
        WHERE {where}
        ORDER BY pg.fecha_pago, pg.id_pago
        LIMIT 50000
        """,
        params,
    )

    columns = [
        "id_pago", "id_pedido", "email", "metodo",
        "monto", "referencia", "fecha_pago",
    ]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)

    for row in rows:
        writer.writerow([safe_cell(row[name]) for name in columns])

    return Response(
        "\ufeff" + out.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="recaudacion.csv"'
        },
    )