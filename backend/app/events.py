from flask import Blueprint, g, jsonify

from .auth import roles_required
from .db import fetch_all, fetch_one, transaction
from .errors import APIError
from .utils import (
    body,
    date_time,
    integer,
    pagination,
    require_row,
    text,
)


bp = Blueprint("events", __name__, url_prefix="/api")

MANAGERS = ("ADMIN", "COOPERADORA", "DOCENTE", "STAFF")


def event_values(data):
    start = date_time(data.get("fecha_inicio"), "fecha_inicio")
    end = date_time(data.get("fecha_fin"), "fecha_fin")

    if end <= start:
        raise APIError("fecha_fin debe ser posterior a fecha_inicio.")

    return (
        integer(data.get("id_espacio"), "id_espacio"),
        text(data.get("titulo"), "titulo", 200),
        text(
            data.get("descripcion"),
            "descripcion",
            20000,
            optional=True,
        ),
        text(data.get("tipo"), "tipo", 50),
        start,
        end,
    )


@bp.get("/spaces")
def spaces():
    return jsonify(
        espacios=fetch_all("SELECT * FROM espacio ORDER BY nombre")
    )


@bp.post("/spaces")
@roles_required("ADMIN", "COOPERADORA")
def create_space():
    data = body({"nombre", "descripcion"})

    with transaction() as cursor:
        cursor.execute(
            "INSERT INTO espacio (nombre, descripcion) VALUES (%s, %s)",
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
        space_id = cursor.lastrowid

    return jsonify(id_espacio=space_id), 201


@bp.get("/events")
def events():
    page, limit, offset = pagination()

    rows = fetch_all(
        """
        SELECT e.*, s.nombre AS espacio
        FROM evento e
        JOIN espacio s ON s.id_espacio = e.id_espacio
        ORDER BY e.fecha_inicio
        LIMIT %s OFFSET %s
        """,
        (limit, offset),
    )

    return jsonify(
        eventos=rows,
        page=page,
        per_page=limit,
        total=fetch_one(
            "SELECT COUNT(*) AS total FROM evento"
        )["total"],
    )


@bp.get("/events/<int:event_id>")
def get_event(event_id):
    return jsonify(
        evento=require_row(
            fetch_one(
                "SELECT * FROM evento WHERE id_evento = %s",
                (event_id,),
            )
        )
    )


@bp.post("/events")
@roles_required(*MANAGERS)
def create_event():
    data = body({
        "id_espacio", "titulo", "descripcion",
        "tipo", "fecha_inicio", "fecha_fin",
    })
    values = event_values(data)

    with transaction() as cursor:
        cursor.execute(
            """
            INSERT INTO evento (
                id_espacio, titulo, descripcion, tipo,
                fecha_inicio, fecha_fin, id_creador
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            values + (g.current_user["id_usuario"],),
        )
        event_id = cursor.lastrowid

    return jsonify(
        evento=fetch_one(
            "SELECT * FROM evento WHERE id_evento = %s",
            (event_id,),
        )
    ), 201


@bp.patch("/events/<int:event_id>")
@roles_required(*MANAGERS)
def update_event(event_id):
    data = body({
        "id_espacio", "titulo", "descripcion",
        "tipo", "fecha_inicio", "fecha_fin",
    })

    with transaction() as cursor:
        cursor.execute(
            "SELECT * FROM evento WHERE id_evento = %s FOR UPDATE",
            (event_id,),
        )
        current = require_row(cursor.fetchone())

        current["fecha_inicio"] = current["fecha_inicio"].isoformat()
        current["fecha_fin"] = current["fecha_fin"].isoformat()
        current.update(data)

        cursor.execute(
            """
            UPDATE evento
            SET id_espacio = %s, titulo = %s, descripcion = %s,
                tipo = %s, fecha_inicio = %s, fecha_fin = %s
            WHERE id_evento = %s
            """,
            event_values(current) + (event_id,),
        )

    return jsonify(
        evento=fetch_one(
            "SELECT * FROM evento WHERE id_evento = %s",
            (event_id,),
        )
    )


@bp.delete("/events/<int:event_id>")
@roles_required("ADMIN", "COOPERADORA")
def delete_event(event_id):
    with transaction() as cursor:
        cursor.execute(
            "SELECT id_evento FROM evento WHERE id_evento = %s "
            "FOR UPDATE",
            (event_id,),
        )
        require_row(cursor.fetchone())

        cursor.execute(
            "DELETE FROM evento WHERE id_evento = %s",
            (event_id,),
        )

    return jsonify(message="Evento eliminado.")