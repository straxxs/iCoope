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


# ----------------------------------------------------------------------
# Categorías
# ----------------------------------------------------------------------

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


@bp.patch("/categories/<int:category_id>")
@roles_required(*MANAGERS)
def update_category(category_id):
    data = body({"nombre", "descripcion"})

    with transaction() as cursor:
        cursor.execute(
            "SELECT * FROM categoria WHERE id_categoria = %s "
            "FOR UPDATE",
            (category_id,),
        )
        current = require_row(
            cursor.fetchone(),
            "Categoría no encontrada.",
        )
        current.update(data)

        cursor.execute(
            """
            UPDATE categoria
            SET nombre = %s, descripcion = %s
            WHERE id_categoria = %s
            """,
            (
                text(current.get("nombre"), "nombre", 100),
                text(
                    current.get("descripcion"),
                    "descripcion",
                    255,
                    optional=True,
                ),
                category_id,
            ),
        )

    return jsonify(
        categoria=fetch_one(
            "SELECT * FROM categoria WHERE id_categoria = %s",
            (category_id,),
        )
    )


@bp.delete("/categories/<int:category_id>")
@roles_required(*MANAGERS)
def delete_category(category_id):
    with transaction() as cursor:
        cursor.execute(
            "SELECT id_categoria FROM categoria "
            "WHERE id_categoria = %s FOR UPDATE",
            (category_id,),
        )
        require_row(cursor.fetchone(), "Categoría no encontrada.")

        cursor.execute(
            "SELECT COUNT(*) AS total FROM producto "
            "WHERE id_categoria = %s",
            (category_id,),
        )

        if cursor.fetchone()["total"] > 0:
            raise APIError(
                "La categoría tiene productos asociados.",
                409,
            )

        cursor.execute(
            "DELETE FROM categoria WHERE id_categoria = %s",
            (category_id,),
        )

    return jsonify(message="Categoría eliminada.")


# ----------------------------------------------------------------------
# Productos
# ----------------------------------------------------------------------

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

    product["stock_total"] = sum(
        variant["stock"] for variant in product["variantes"]
    )

    # Para entradas, el stock de las variantes es el aforo disponible.
    if product["es_evento"]:
        product["lugares_disponibles"] = product["stock_total"]

    return product


def query_flag(name):
    value = request.args.get(name)

    if value is None:
        return None

    if value not in {"true", "false"}:
        raise APIError(f"{name} debe ser true o false.")

    return value == "true"


def list_products(only_active):
    page, limit, offset = pagination()
    conditions = ["p.activo = TRUE"] if only_active else []
    params = []

    category = request.args.get("id_categoria")

    if category is not None:
        try:
            category_id = int(category)
        except ValueError:
            raise APIError("id_categoria debe ser un entero.")

        conditions.append("p.id_categoria = %s")
        params.append(integer(category_id, "id_categoria"))

    event = query_flag("es_evento")

    if event is not None:
        conditions.append("p.es_evento = %s")
        params.append(event)

    in_stock = query_flag("con_stock")

    if in_stock is not None:
        conditions.append(
            ("" if in_stock else "NOT ")
            + "EXISTS (SELECT 1 FROM variante_producto v "
            "WHERE v.id_producto = p.id_producto AND v.stock > 0)"
        )

    search = request.args.get("q")

    if search:
        conditions.append("p.nombre LIKE %s")
        params.append(f"%{text(search, 'q', 150)}%")

    where = " AND ".join(conditions) or "TRUE"

    rows = fetch_all(
        f"""
        SELECT p.*, c.nombre AS categoria,
               COALESCE((
                   SELECT SUM(v.stock) FROM variante_producto v
                   WHERE v.id_producto = p.id_producto
               ), 0) AS stock_total
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
        row["stock_total"] = int(row["stock_total"])

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


@bp.get("/products")
def products():
    return list_products(only_active=True)


@bp.get("/products/<int:product_id>")
def get_product(product_id):
    return jsonify(producto=product_detail(product_id))


@bp.get("/admin/products")
@roles_required(*MANAGERS)
def admin_products():
    return list_products(only_active=False)


@bp.get("/admin/products/<int:product_id>")
@roles_required(*MANAGERS)
def admin_get_product(product_id):
    return jsonify(
        producto=product_detail(product_id, only_active=False)
    )


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


# ----------------------------------------------------------------------
# Variantes e inventario
# ----------------------------------------------------------------------

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


@bp.patch("/variants/<int:variant_id>")
@roles_required(*MANAGERS)
def update_variant(variant_id):
    data = body({"nombre"})
    name = text(data.get("nombre"), "nombre", 100)

    with transaction() as cursor:
        cursor.execute(
            "SELECT id_variante FROM variante_producto "
            "WHERE id_variante = %s FOR UPDATE",
            (variant_id,),
        )
        require_row(cursor.fetchone(), "Variante no encontrada.")

        cursor.execute(
            "UPDATE variante_producto SET nombre = %s "
            "WHERE id_variante = %s",
            (name, variant_id),
        )

    return jsonify(
        variante=fetch_one(
            "SELECT * FROM variante_producto WHERE id_variante = %s",
            (variant_id,),
        )
    )


@bp.delete("/variants/<int:variant_id>")
@roles_required(*MANAGERS)
def delete_variant(variant_id):
    with transaction() as cursor:
        cursor.execute(
            "SELECT id_variante FROM variante_producto "
            "WHERE id_variante = %s FOR UPDATE",
            (variant_id,),
        )
        require_row(cursor.fetchone(), "Variante no encontrada.")

        cursor.execute(
            "SELECT 1 FROM detalle_pedido "
            "WHERE id_variante = %s LIMIT 1",
            (variant_id,),
        )

        if cursor.fetchone() is not None:
            raise APIError(
                "La variante tiene pedidos asociados. "
                "Pon su stock en 0 o desactiva el producto.",
                409,
            )

        cursor.execute(
            "DELETE FROM variante_producto WHERE id_variante = %s",
            (variant_id,),
        )

    return jsonify(message="Variante eliminada.")


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


# ----------------------------------------------------------------------
# Imágenes
# ----------------------------------------------------------------------

@bp.post("/products/<int:product_id>/images")
@roles_required(*MANAGERS)
def add_image(product_id):
    data = body({"url_imagen", "orden"})
    url = text(data.get("url_imagen"), "url_imagen", 500)
    order = integer(data.get("orden", 1), "orden")

    if not url.startswith(("http://", "https://", "/")):
        raise APIError(
            "url_imagen debe ser http(s) o una ruta que empiece con /."
        )

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


@bp.delete("/images/<int:image_id>")
@roles_required(*MANAGERS)
def delete_image(image_id):
    with transaction() as cursor:
        cursor.execute(
            "SELECT id_imagen FROM producto_imagen "
            "WHERE id_imagen = %s FOR UPDATE",
            (image_id,),
        )
        require_row(cursor.fetchone(), "Imagen no encontrada.")

        cursor.execute(
            "DELETE FROM producto_imagen WHERE id_imagen = %s",
            (image_id,),
        )

    return jsonify(message="Imagen eliminada.")

@bp.get("/inventory")
@roles_required(*MANAGERS)
def inventory():
    page, limit, offset = pagination()
    conditions = ["p.activo = TRUE"]
    params = []

    max_stock = request.args.get("max_stock")

    if max_stock is not None:
        try:
            threshold = int(max_stock)
        except ValueError:
            raise APIError("max_stock debe ser un entero.")

        conditions.append("v.stock <= %s")
        params.append(integer(threshold, "max_stock", minimum=0))

    where = " AND ".join(conditions)

    rows = fetch_all(
        f"""
        SELECT v.id_variante, v.nombre AS variante, v.stock,
               p.id_producto, p.nombre AS producto, p.es_evento
        FROM variante_producto v
        JOIN producto p ON p.id_producto = v.id_producto
        WHERE {where}
        ORDER BY v.stock, v.id_variante
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )

    for row in rows:
        row["es_evento"] = bool(row["es_evento"])

    return jsonify(inventario=rows, page=page, per_page=limit)