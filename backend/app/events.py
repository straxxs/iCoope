from flask import Blueprint, g, jsonify, request

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
MODERATORS = {"ADMIN", "COOPERADORA"}


def check_owner(event):
    if (
        event["id_creador"] != g.current_user["id_usuario"]
        and not MODERATORS.intersection(g.current_user["roles"])
    ):
        raise APIError("No puedes modificar un evento ajeno.", 403)


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

def check_overlap(cursor, values, exclude_id=0):
    space_id, start, end = values[0], values[4], values[5]

    cursor.execute(
        """
        SELECT titulo FROM evento
        WHERE id_espacio = %s
          AND fecha_inicio < %s AND fecha_fin > %s
          AND id_evento <> %s
        LIMIT 1 FOR UPDATE
        """,
        (space_id, end, start, exclude_id),
    )
    clash = cursor.fetchone()

    if clash is not None:
        raise APIError(
            f"El espacio ya está reservado: «{clash['titulo']}».",
            409,
        )

# ----------------------------------------------------------------------
# Disponibilidad de espacios
# ----------------------------------------------------------------------

def lock_space(cursor, space_id):
    # Bloquear el espacio serializa las reservas concurrentes sobre él,
    # de modo que dos eventos no puedan colarse a la vez en el mismo hueco.
    cursor.execute(
        "SELECT id_espacio FROM espacio WHERE id_espacio = %s FOR UPDATE",
        (space_id,),
    )

    if cursor.fetchone() is None:
        raise APIError("El espacio no existe.")


def free_spaces(cursor, space_id, start, end):
    cursor.execute(
        """
        SELECT s.id_espacio, s.nombre
        FROM espacio s
        WHERE s.id_espacio <> %s
          AND NOT EXISTS (
              SELECT 1
              FROM evento e
              WHERE e.id_espacio = s.id_espacio
                AND e.fecha_inicio < %s
                AND e.fecha_fin > %s
          )
        ORDER BY s.nombre
        """,
        (space_id, end, start),
    )

    return cursor.fetchall()


def next_free_slot(cursor, space_id, start, end, exclude_id):
    duration = end - start

    sql = (
        "SELECT fecha_inicio, fecha_fin FROM evento "
        "WHERE id_espacio = %s AND fecha_fin > %s"
    )
    params = [space_id, start]

    if exclude_id is not None:
        sql += " AND id_evento <> %s"
        params.append(exclude_id)

    sql += " ORDER BY fecha_inicio LIMIT 500"

    cursor.execute(sql, tuple(params))

    candidate = start

    for row in cursor.fetchall():
        if row["fecha_inicio"] >= candidate + duration:
            break

        if row["fecha_fin"] > candidate:
            candidate = row["fecha_fin"]

    return {
        "fecha_inicio": candidate,
        "fecha_fin": candidate + duration,
    }


def ensure_available(cursor, space_id, start, end, exclude_id=None):
    lock_space(cursor, space_id)

    sql = """
        SELECT id_evento, titulo, fecha_inicio, fecha_fin
        FROM evento
        WHERE id_espacio = %s AND fecha_inicio < %s AND fecha_fin > %s
    """
    params = [space_id, end, start]

    if exclude_id is not None:
        sql += " AND id_evento <> %s"
        params.append(exclude_id)

    sql += " ORDER BY fecha_inicio"

    cursor.execute(sql, tuple(params))
    conflicts = cursor.fetchall()

    if not conflicts:
        return

    raise APIError(
        "El espacio ya está reservado en ese horario.",
        409,
        extra={
            "conflictos": conflicts,
            "espacios_libres": free_spaces(
                cursor, space_id, start, end
            ),
            "proximo_horario_libre": next_free_slot(
                cursor, space_id, start, end, exclude_id
            ),
        },
    )


# ----------------------------------------------------------------------
# Espacios
# ----------------------------------------------------------------------

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


@bp.patch("/spaces/<int:space_id>")
@roles_required("ADMIN", "COOPERADORA")
def update_space(space_id):
    data = body({"nombre", "descripcion"})

    with transaction() as cursor:
        cursor.execute(
            "SELECT * FROM espacio WHERE id_espacio = %s FOR UPDATE",
            (space_id,),
        )
        current = require_row(
            cursor.fetchone(),
            "Espacio no encontrado.",
        )
        current.update(data)

        cursor.execute(
            "UPDATE espacio SET nombre = %s, descripcion = %s "
            "WHERE id_espacio = %s",
            (
                text(current.get("nombre"), "nombre", 100),
                text(
                    current.get("descripcion"),
                    "descripcion",
                    255,
                    optional=True,
                ),
                space_id,
            ),
        )

    return jsonify(
        espacio=fetch_one(
            "SELECT * FROM espacio WHERE id_espacio = %s",
            (space_id,),
        )
    )


# ----------------------------------------------------------------------
# Eventos (calendario)
# ----------------------------------------------------------------------

@bp.get("/events")
def events():
    page, limit, offset = pagination()
    conditions = []
    params = []

    # Un evento entra en la ventana [desde, hasta) si se solapa con ella.
    since = request.args.get("desde")

    if since:
        conditions.append("e.fecha_fin > %s")
        params.append(date_time(since, "desde"))

    until = request.args.get("hasta")

    if until:
        conditions.append("e.fecha_inicio < %s")
        params.append(date_time(until, "hasta"))

    space = request.args.get("id_espacio")

    if space is not None:
        try:
            space_id = int(space)
        except ValueError:
            raise APIError("id_espacio debe ser un entero.")

        conditions.append("e.id_espacio = %s")
        params.append(integer(space_id, "id_espacio"))

    kind = request.args.get("tipo")

    if kind:
        conditions.append("e.tipo = %s")
        params.append(text(kind, "tipo", 50))

    where = " AND ".join(conditions) or "TRUE"

    rows = fetch_all(
        f"""
        SELECT e.*, s.nombre AS espacio
        FROM evento e
        JOIN espacio s ON s.id_espacio = e.id_espacio
        WHERE {where}
        ORDER BY e.fecha_inicio
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )

    return jsonify(
        eventos=rows,
        page=page,
        per_page=limit,
        total=fetch_one(
            f"SELECT COUNT(*) AS total FROM evento e WHERE {where}",
            tuple(params),
        )["total"],
    )


@bp.get("/events/<int:event_id>")
def get_event(event_id):
    return jsonify(
        evento=require_row(
            fetch_one(
                """
                SELECT e.*, s.nombre AS espacio
                FROM evento e
                JOIN espacio s ON s.id_espacio = e.id_espacio
                WHERE e.id_evento = %s
                """,
                (event_id,),
            ),
            "Evento no encontrado.",
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
        ensure_available(cursor, values[0], values[4], values[5])
        check_overlap(cursor, values)        

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
        current = require_row(cursor.fetchone(), "Evento no encontrado.")
        check_owner(current)

        current["fecha_inicio"] = current["fecha_inicio"].isoformat()
        current["fecha_fin"] = current["fecha_fin"].isoformat()
        current.update(data)

        values = event_values(current)

        ensure_available(
            cursor,
            values[0],
            values[4],
            values[5],
            exclude_id=event_id,
        )
        values = event_values(current)
        check_overlap(cursor, values, event_id)

        cursor.execute(
            """
            UPDATE evento
            SET id_espacio = %s, titulo = %s, descripcion = %s,
                tipo = %s, fecha_inicio = %s, fecha_fin = %s
            WHERE id_evento = %s
            """,
            values + (event_id,),
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
        require_row(cursor.fetchone(), "Evento no encontrado.")

        cursor.execute(
            "DELETE FROM evento WHERE id_evento = %s",
            (event_id,),
        )

    return jsonify(message="Evento eliminado.")