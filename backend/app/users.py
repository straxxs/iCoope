from flask import Blueprint, g, jsonify, request

from .auth import roles_required
from .db import fetch_all, fetch_one, transaction
from .errors import APIError
from .utils import boolean


bp = Blueprint("users", __name__, url_prefix="/api/users")


@bp.get("")
@roles_required("ADMIN")
def list_users():
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        raise APIError("La paginación debe contener enteros.")
    if page < 1 or not 1 <= per_page <= 100:
        raise APIError("page debe ser mayor que cero y per_page entre 1 y 100.")

    query = request.args.get("q", "").strip()
    where = ""
    params = []
    if query:
        where = "WHERE u.nombre LIKE %s OR u.apellido LIKE %s OR u.email LIKE %s"
        pattern = f"%{query}%"
        params.extend((pattern, pattern, pattern))

    total_row = fetch_one(
        f"SELECT COUNT(*) AS total FROM usuario u {where}", tuple(params)
    )
    users = fetch_all(
        f"""
        SELECT u.id_usuario, u.nombre, u.apellido, u.email, u.activo,
               GROUP_CONCAT(r.nombre ORDER BY r.nombre SEPARATOR ',') AS roles
        FROM usuario u
        LEFT JOIN usuario_rol ur ON ur.id_usuario = u.id_usuario
        LEFT JOIN rol r ON r.id_rol = ur.id_rol
        {where}
        GROUP BY u.id_usuario, u.nombre, u.apellido, u.email, u.activo
        ORDER BY u.apellido, u.nombre, u.id_usuario
        LIMIT %s OFFSET %s
        """,
        tuple(params + [per_page, (page - 1) * per_page]),
    )
    for user in users:
        user["activo"] = bool(user["activo"])
        user["roles"] = user["roles"].split(",") if user["roles"] else []

    return jsonify(
        usuarios=users, total=total_row["total"], page=page, per_page=per_page
    )

@bp.patch("/<int:user_id>/active")
@roles_required("ADMIN")
def set_user_active(user_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"activo"}:
        raise APIError("Envía el campo activo como true o false.")
    active = boolean(data["activo"], "activo")

    if user_id == g.current_user["id_usuario"] and not active:
        raise APIError("No puedes desactivar tu propio usuario.", 409)

    with transaction() as cursor:
        cursor.execute(
            "UPDATE usuario SET activo = %s WHERE id_usuario = %s",
            (active, user_id),
        )
        if cursor.rowcount == 0:
            exists = fetch_one("SELECT id_usuario FROM usuario WHERE id_usuario = %s", (user_id,))
            if exists is None:
                raise APIError("Usuario no encontrado.", 404)

    return jsonify(id_usuario=user_id, activo=active)
