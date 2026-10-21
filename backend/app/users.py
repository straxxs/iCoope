from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from .auth import get_user, jwt_required, roles_required
from .db import fetch_all, fetch_one, transaction
from .errors import APIError
from .utils import body, boolean, pagination, require_row, text


bp = Blueprint("users", __name__, url_prefix="/api")


@bp.get("/users")
@roles_required("ADMIN")
def list_users():
    page, limit, offset = pagination()
    conditions = []
    params = []

    search = request.args.get("q")

    if search:
        like = f"%{text(search, 'q', 150)}%"
        conditions.append(
            "(u.nombre LIKE %s OR u.apellido LIKE %s OR u.email LIKE %s)"
        )
        params.extend([like, like, like])

    role = request.args.get("rol")

    if role:
        conditions.append(
            """
            EXISTS (
                SELECT 1
                FROM usuario_rol ur
                JOIN rol r ON r.id_rol = ur.id_rol
                WHERE ur.id_usuario = u.id_usuario AND r.nombre = %s
            )
            """
        )
        params.append(text(role, "rol", 50))

    active = request.args.get("activo")

    if active is not None:
        if active not in {"true", "false"}:
            raise APIError("activo debe ser true o false.")

        conditions.append("u.activo = %s")
        params.append(active == "true")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = fetch_all(
        f"""
        SELECT u.id_usuario, u.nombre, u.apellido, u.email,
               u.telefono, u.activo, u.fecha_registro
        FROM usuario u
        {where}
        ORDER BY u.id_usuario DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )

    total = fetch_one(
        f"SELECT COUNT(*) AS total FROM usuario u {where}",
        tuple(params),
    )["total"]

    roles_by_user = {}

    if rows:
        placeholders = ", ".join(["%s"] * len(rows))

        for item in fetch_all(
            f"""
            SELECT ur.id_usuario, r.nombre
            FROM usuario_rol ur
            JOIN rol r ON r.id_rol = ur.id_rol
            WHERE ur.id_usuario IN ({placeholders})
            ORDER BY r.nombre
            """,
            tuple(row["id_usuario"] for row in rows),
        ):
            roles_by_user.setdefault(item["id_usuario"], []).append(
                item["nombre"]
            )

    for row in rows:
        row["activo"] = bool(row["activo"])
        row["roles"] = roles_by_user.get(row["id_usuario"], [])

    return jsonify(
        usuarios=rows,
        page=page,
        per_page=limit,
        total=total,
    )


@bp.get("/users/<int:user_id>")
@roles_required("ADMIN")
def get_user_detail(user_id):
    return jsonify(
        usuario=require_row(get_user(user_id), "Usuario no encontrado.")
    )


@bp.patch("/users/<int:user_id>/active")
@roles_required("ADMIN")
def set_active(user_id):
    data = body({"activo"})
    active = boolean(data.get("activo"), "activo")

    # Quien llama es un ADMIN activo, así que mientras no pueda
    # desactivarse a sí mismo siempre queda al menos un admin activo.
    if not active and user_id == g.current_user["id_usuario"]:
        raise APIError("No puedes desactivar tu propia cuenta.", 409)

    with transaction() as cursor:
        cursor.execute(
            "SELECT id_usuario FROM usuario "
            "WHERE id_usuario = %s FOR UPDATE",
            (user_id,),
        )
        require_row(cursor.fetchone(), "Usuario no encontrado.")

        cursor.execute(
            "UPDATE usuario SET activo = %s WHERE id_usuario = %s",
            (active, user_id),
        )

    return jsonify(usuario=get_user(user_id))


@bp.post("/auth/change-password")
@jwt_required
def change_password():
    data = body({"password_actual", "password_nueva"})
    current = data.get("password_actual")
    new = data.get("password_nueva")

    if not isinstance(current, str) or not 1 <= len(current) <= 128:
        raise APIError("La contraseña actual no es válida.")

    if not isinstance(new, str) or not 8 <= len(new) <= 128:
        raise APIError(
            "La contraseña nueva debe tener entre 8 y 128 caracteres."
        )

    if new == current:
        raise APIError("La contraseña nueva debe ser distinta.")

    user_id = g.current_user["id_usuario"]

    row = require_row(
        fetch_one(
            "SELECT password_hash FROM usuario WHERE id_usuario = %s",
            (user_id,),
        )
    )

    if not check_password_hash(row["password_hash"], current):
        raise APIError("La contraseña actual es incorrecta.", 403)

    with transaction() as cursor:
        cursor.execute(
            "UPDATE usuario SET password_hash = %s WHERE id_usuario = %s",
            (generate_password_hash(new), user_id),
        )

    return jsonify(message="Contraseña actualizada.")