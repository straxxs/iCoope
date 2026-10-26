from flask import Blueprint, g, jsonify, request

from .auth import roles_required
from .db import fetch_all, fetch_one, transaction
from .errors import APIError
from .utils import (
    body,
    boolean,
    pagination,
    require_row,
    text,
)


bp = Blueprint("community", __name__, url_prefix="/api")

PUBLISHERS = ("ADMIN", "COOPERADORA", "DOCENTE", "STAFF")
MODERATORS = {"ADMIN", "COOPERADORA"}


def check_owner(post):
    if (
        post["id_autor"] != g.current_user["id_usuario"]
        and not MODERATORS.intersection(g.current_user["roles"])
    ):
        raise APIError("No puedes modificar una publicación ajena.", 403)


def post_values(data):
    return (
        text(data.get("titulo"), "titulo", 200),
        text(data.get("contenido"), "contenido", 15000),
        boolean(data.get("urgente", False), "urgente"),
        boolean(data.get("publicado", True), "publicado"),
    )


@bp.get("/posts")
@bp.get("/v1/foro")
def posts():
    page, limit, offset = pagination()
    condition = "publicado = TRUE"

    urgent = request.args.get("urgente")

    if urgent is not None:
        if urgent not in {"true", "false"}:
            raise APIError("urgente debe ser true o false.")

        condition += " AND urgente = " + (
            "TRUE" if urgent == "true" else "FALSE"
        )

    return jsonify(
        publicaciones=fetch_all(
            f"""
            SELECT *
            FROM publicacion
            WHERE {condition}
            ORDER BY urgente DESC, fecha_publicacion DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        ),
        page=page,
        per_page=limit,
        total=fetch_one(
            f"SELECT COUNT(*) AS total FROM publicacion "
            f"WHERE {condition}"
        )["total"],
    )


@bp.get("/announcements")
def announcements():
    page, limit, offset = pagination()

    return jsonify(
        anuncios=fetch_all(
            """
            SELECT * FROM publicacion
            WHERE publicado = TRUE AND urgente = TRUE
            ORDER BY fecha_publicacion DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        ),
        page=page,
        per_page=limit,
    )


@bp.get("/posts/<int:post_id>")
def get_post(post_id):
    return jsonify(
        publicacion=require_row(
            fetch_one(
                """
                SELECT * FROM publicacion
                WHERE id_publicacion = %s AND publicado = TRUE
                """,
                (post_id,),
            )
        )
    )


@bp.post("/posts")
@bp.post("/v1/foro")
@roles_required(*PUBLISHERS)
def create_post():
    data = body({"titulo", "contenido", "urgente", "publicado"})
    values = post_values(data)

    with transaction() as cursor:
        cursor.execute(
            """
            INSERT INTO publicacion (
                titulo, contenido, urgente, publicado, id_autor
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            values + (g.current_user["id_usuario"],),
        )
        post_id = cursor.lastrowid

    return jsonify(
        publicacion=fetch_one(
            "SELECT * FROM publicacion WHERE id_publicacion = %s",
            (post_id,),
        )
    ), 201


@bp.patch("/posts/<int:post_id>")
@roles_required(*PUBLISHERS)
def update_post(post_id):
    data = body({"titulo", "contenido", "urgente", "publicado"})

    with transaction() as cursor:
        cursor.execute(
            "SELECT * FROM publicacion WHERE id_publicacion = %s "
            "FOR UPDATE",
            (post_id,),
        )
        current = require_row(cursor.fetchone())
        check_owner(current)

        current["urgente"] = bool(current["urgente"])
        current["publicado"] = bool(current["publicado"])
        current.update(data)

        cursor.execute(
            """
            UPDATE publicacion
            SET titulo = %s, contenido = %s,
                urgente = %s, publicado = %s
            WHERE id_publicacion = %s
            """,
            post_values(current) + (post_id,),
        )

    return jsonify(
        publicacion=fetch_one(
            "SELECT * FROM publicacion WHERE id_publicacion = %s",
            (post_id,),
        )
    )


@bp.delete("/posts/<int:post_id>")
@roles_required(*PUBLISHERS)
def delete_post(post_id):
    with transaction() as cursor:
        cursor.execute(
            "SELECT * FROM publicacion WHERE id_publicacion = %s "
            "FOR UPDATE",
            (post_id,),
        )
        post = require_row(cursor.fetchone())
        check_owner(post)

        cursor.execute(
            "UPDATE publicacion SET publicado = FALSE "
            "WHERE id_publicacion = %s",
            (post_id,),
        )

    return jsonify(message="Publicación ocultada.")