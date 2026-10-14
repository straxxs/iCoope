from flask import Blueprint, jsonify, request

from .auth import roles_required
from .db import fetch_all, fetch_one, transaction
from .errors import APIError
from .utils import (
    body,
    boolean,
    date_time,
    integer,
    money,
    pagination,
    require_row,
    text,
)


bp = Blueprint("catalog", __name__, url_prefix="/api")

MANAGERS = ("ADMIN", "COOPERADORA", "STAFF")


@bp.get("/categories")
def categories():
    return jsonify(
        categorias=fetch_all(
            "SELECT * FROM categoria ORDER BY nombre"
        )
    )


@bp.post("/categories")
@roles_required(*MANAGERS)
def create_category():
    data = body({"nombre", "descripcion"})

    with transaction() as cursor:
        cursor.execute(
            """
            INSERT INTO categoria (nombre, descripcion)
            VALUES (%s, %s)
            """,
            (
                text(data.get("nombre"), "nombre", 100),
                text(
                    data.get("descripcion"),
                    "descripcion",
                    255,
                    optional=True,
                ),
            ),
        )
        category_id = cursor.lastrowid

    return jsonify(
        categoria=fetch_one(
            "SELECT * FROM categoria WHERE id_categoria = %s",
            (category_id,),
        )
    ), 201


def product_values(data):
    event = boolean(data.get("es_evento", False), "es_evento")
    event_date = data.get("fecha_evento")

    if event:
        event_date = date_time(event_date, "fecha_evento")
    elif event_date is not None:
        raise APIError(
            "Un producto que no es evento no puede tener fecha_evento."
        )

    return (
        integer(data.get("id_categoria"), "id_categoria"),
        text(data.get("nombre"), "nombre", 150),
        text(
            data.get("descripcion"),
            "descripcion",
            20000,
            optional=True,
        ),
        money(data.get("precio")),
        event,
        event_date,
        boolean(data.get("activo", True), "activo"),
    )


def product_detail(product_id, only_active=True):
    sql = "SELECT * FROM producto WHERE id_producto = %s"

    if only_active:
        sql += " AND activo = TRUE"

    product = require_row(
        fetch_one(sql, (product_id,)),
        "Producto no encontrado.",
    )

    product["activo"] = bool(product["activo"])
    product["es_evento"] = bool(product["es_evento"])

    product["variantes"] = fetch_all(
        """
        SELECT * FROM variante_producto
        WHERE id_producto = %s
        ORDER BY id_variante
        """,
        (product_id,),
    )

    product["imagenes"] = fetch_all(
        """
        SELECT * FROM producto_imagen
        WHERE id_producto = %s
        ORDER BY orden
        """,
        (product_id,),
    )

    return product


@bp.get("/products")
def products():
    page, limit, offset = pagination()
    conditions = ["p.activo = TRUE"]
    params = []

    category = request.args.get("id_categoria")

    if category is not None:
        try:
            category_id = int(category)
        except ValueError:
            raise APIError("id_categoria debe ser un entero.")

        conditions.append("p.id_categoria = %s")
        params.append(integer(category_id, "id_categoria"))

    event = request.args.get("es_evento")

    if event is not None:
        if event not in {"true", "false"}:
            raise APIError("es_evento debe ser true o false.")

        conditions.append("p.es_evento = %s")
        params.append(event == "true")

    search = request.args.get("q")

    if search:
        conditions.append("p.nombre LIKE %s")
        params.append(f"%{text(search, 'q', 150)}%")

    where = " AND ".join(conditions)

    rows = fetch_all(
        f"""
        SELECT p.*, c.nombre AS categoria
        FROM producto p
        JOIN categoria c ON c.id_categoria = p.id_categoria
        WHERE {where}
        ORDER BY p.id_producto DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )

    for row in rows:
        row["activo"] = bool(row["activo"])
        row["es_evento"] = bool(row["es_evento"])

    total = fetch_one(
        f"SELECT COUNT(*) AS total FROM producto p WHERE {where}",
        tuple(params),
    )["total"]

    return jsonify(
        productos=rows,
        page=page,
        per_page=limit,
        total=total,
    )


@bp.get("/products/<int:product_id>")
def get_product(product_id):
    return jsonify(producto=product_detail(product_id))


@bp.post("/products")
@roles_required(*MANAGERS)
def create_product():
    data = body({
        "id_categoria", "nombre", "descripcion", "precio",
        "es_evento", "fecha_evento", "activo",
    })
    values = product_values(data)

    with transaction() as cursor:
        cursor.execute(
            """
            INSERT INTO producto (
                id_categoria, nombre, descripcion, precio,
                es_evento, fecha_evento, activo
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            values,
        )
        product_id = cursor.lastrowid

    return jsonify(
        producto=product_detail(product_id, only_active=False)
    ), 201


@bp.patch("/products/<int:product_id>")
@roles_required(*MANAGERS)
def update_product(product_id):
    data = body({
        "id_categoria", "nombre", "descripcion", "precio",
        "es_evento", "fecha_evento", "activo",
    })

    with transaction() as cursor:
        cursor.execute(
            "SELECT * FROM producto WHERE id_producto = %s FOR UPDATE",
            (product_id,),
        )
        current = require_row(cursor.fetchone())

        current["activo"] = bool(current["activo"])
        current["es_evento"] = bool(current["es_evento"])

        if current["fecha_evento"] is not None:
            current["fecha_evento"] = current["fecha_evento"].isoformat()

        current.update(data)
        values = product_values(current)

        cursor.execute(
            """
            UPDATE producto
            SET id_categoria = %s, nombre = %s, descripcion = %s,
                precio = %s, es_evento = %s, fecha_evento = %s,
                activo = %s
            WHERE id_producto = %s
            """,
            values + (product_id,),
        )

    return jsonify(
        producto=product_detail(product_id, only_active=False)
    )


@bp.delete("/products/<int:product_id>")
@roles_required(*MANAGERS)
def deactivate_product(product_id):
    with transaction() as cursor:
        cursor.execute(
            "SELECT id_producto FROM producto "
            "WHERE id_producto = %s FOR UPDATE",
            (product_id,),
        )
        require_row(cursor.fetchone())

        cursor.execute(
            "UPDATE producto SET activo = FALSE WHERE id_producto = %s",
            (product_id,),
        )

    return jsonify(message="Producto desactivado.")


@bp.post("/products/<int:product_id>/variants")
@roles_required(*MANAGERS)
def create_variant(product_id):
    data = body({"nombre", "stock"})
    name = text(data.get("nombre"), "nombre", 100)
    stock = integer(data.get("stock", 0), "stock", minimum=0)

    with transaction() as cursor:
        cursor.execute(
            "SELECT id_producto FROM producto WHERE id_producto = %s",
            (product_id,),
        )
        require_row(cursor.fetchone())

        cursor.execute(
            """
            INSERT INTO variante_producto (id_producto, nombre, stock)
            VALUES (%s, %s, %s)
            """,
            (product_id, name, stock),
        )
        variant_id = cursor.lastrowid

    return jsonify(
        variante=fetch_one(
            "SELECT * FROM variante_producto WHERE id_variante = %s",
            (variant_id,),
        )
    ), 201


@bp.patch("/variants/<int:variant_id>/stock")
@roles_required(*MANAGERS)
def adjust_stock(variant_id):
    data = body({"delta"})
    delta = integer(
        data.get("delta"),
        "delta",
        minimum=-2147483647,
    )

    with transaction() as cursor:
        cursor.execute(
            "SELECT * FROM variante_producto "
            "WHERE id_variante = %s FOR UPDATE",
            (variant_id,),
        )
        variant = require_row(cursor.fetchone())

        new_stock = variant["stock"] + delta

        if not 0 <= new_stock <= 2147483647:
            raise APIError("El ajuste produce un stock inválido.", 409)

        cursor.execute(
            "UPDATE variante_producto SET stock = %s "
            "WHERE id_variante = %s",
            (new_stock, variant_id),
        )

    return jsonify(
        id_variante=variant_id,
        stock=new_stock,
    )


@bp.post("/products/<int:product_id>/images")
@roles_required(*MANAGERS)
def add_image(product_id):
    data = body({"url_imagen", "orden"})
    url = text(data.get("url_imagen"), "url_imagen", 500)
    order = integer(data.get("orden", 1), "orden")

    with transaction() as cursor:
        cursor.execute(
            "SELECT id_producto FROM producto WHERE id_producto = %s",
            (product_id,),
        )
        require_row(cursor.fetchone())

        cursor.execute(
            """
            INSERT INTO producto_imagen (id_producto, url_imagen, orden)
            VALUES (%s, %s, %s)
            """,
            (product_id, url, order),
        )
        image_id = cursor.lastrowid

    return jsonify(id_imagen=image_id), 201