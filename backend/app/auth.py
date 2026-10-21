import re
from datetime import datetime, timedelta, timezone
from functools import wraps

import click
import jwt
import pymysql
from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from .db import fetch_all, fetch_one, transaction
from .errors import APIError
from .utils import body, text


bp = Blueprint("auth", __name__, url_prefix="/api/auth")

DUMMY_HASH = generate_password_hash("clave-interna-de-comprobacion")


def get_user(user_id):
    user = fetch_one(
        """
        SELECT id_usuario, nombre, apellido, email, telefono,
               activo, fecha_registro
        FROM usuario
        WHERE id_usuario = %s
        """,
        (user_id,),
    )

    if user is None:
        return None

    user["activo"] = bool(user["activo"])
    user["roles"] = [
        row["nombre"]
        for row in fetch_all(
            """
            SELECT r.nombre
            FROM rol r
            JOIN usuario_rol ur ON ur.id_rol = r.id_rol
            WHERE ur.id_usuario = %s
            ORDER BY r.nombre
            """,
            (user_id,),
        )
    ]

    return user


def normalize_email(value):
    email = text(value, "email", 150).lower()

    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise APIError("El email no es válido.")

    return email


def create_user(data, role_name):
    nombre = text(data.get("nombre"), "nombre", 100)
    apellido = text(data.get("apellido"), "apellido", 100)
    email = normalize_email(data.get("email"))

    password = data.get("password")

    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise APIError(
            "La contraseña debe tener entre 8 y 128 caracteres."
        )

    telefono = text(
        data.get("telefono"),
        "telefono",
        30,
        optional=True,
    )

    password_hash = generate_password_hash(password)

    try:
        with transaction() as cursor:
            cursor.execute(
                "SELECT id_rol FROM rol WHERE nombre = %s",
                (role_name,),
            )
            role = cursor.fetchone()

            if role is None:
                raise APIError(
                    "El rol no existe. Comprueba los datos iniciales.",
                    500,
                )

            cursor.execute(
                """
                INSERT INTO usuario
                    (nombre, apellido, email, password_hash, telefono)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (nombre, apellido, email, password_hash, telefono),
            )
            user_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO usuario_rol (id_usuario, id_rol)
                VALUES (%s, %s)
                """,
                (user_id, role["id_rol"]),
            )
    except pymysql.err.IntegrityError as error:
        if error.args[0] == 1062:
            raise APIError("El email ya está registrado.", 409) from error
        raise

    return get_user(user_id)


def authenticate():
    if "current_user" in g:
        return

    parts = request.headers.get("Authorization", "").split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise APIError("Debes enviar un token Bearer.", 401)

    try:
        payload = jwt.decode(
            parts[1],
            current_app.config["SECRET_KEY"],
            algorithms=["HS256"],
            issuer=current_app.config["JWT_ISSUER"],
            audience=current_app.config["JWT_AUDIENCE"],
            options={
                "require": [
                    "sub", "iat", "nbf", "exp", "iss", "aud", "type"
                ]
            },
        )
    except jwt.ExpiredSignatureError:
        raise APIError("El token expiró.", 401)
    except jwt.InvalidTokenError:
        raise APIError("El token no es válido.", 401)

    subject = payload.get("sub")

    if (
        payload.get("type") != "access"
        or not isinstance(subject, str)
        or not subject.isascii()
        or not subject.isdecimal()
        or not 1 <= len(subject) <= 10
        or not 1 <= int(subject) <= 2147483647
    ):
        raise APIError("El token no es válido.", 401)

    user = get_user(int(subject))

    if user is None or not user["activo"]:
        raise APIError("Usuario inexistente o desactivado.", 401)

    g.current_user = user


def jwt_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        authenticate()
        return view(*args, **kwargs)

    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            authenticate()

            if not set(roles).intersection(g.current_user["roles"]):
                raise APIError("No tienes permisos.", 403)

            return view(*args, **kwargs)

        return wrapped

    return decorator


def is_admin():
    return "ADMIN" in g.current_user["roles"]


@bp.post("/register")
def register():
    if not current_app.config["PUBLIC_REGISTRATION_ENABLED"]:
        raise APIError("El registro público está deshabilitado.", 403)

    role = current_app.config["PUBLIC_REGISTRATION_ROLE"]

    if role not in {"ALUMNO", "PADRE"}:
        raise APIError("Rol público mal configurado.", 500)

    data = body({"nombre", "apellido", "email", "password", "telefono"})

    return jsonify(usuario=create_user(data, role)), 201


@bp.post("/login")
def login():
    data = body({"email", "password"})
    email = normalize_email(data.get("email"))
    password = data.get("password")

    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        raise APIError("Email o contraseña incorrectos.", 401)

    row = fetch_one(
        """
        SELECT id_usuario, password_hash, activo
        FROM usuario
        WHERE email = %s
        """,
        (email,),
    )

    valid = check_password_hash(
        row["password_hash"] if row else DUMMY_HASH,
        password,
    )

    if row is None or not valid or not row["activo"]:
        raise APIError("Email o contraseña incorrectos.", 401)

    now = datetime.now(timezone.utc)
    minutes = current_app.config["JWT_ACCESS_TOKEN_MINUTES"]

    token = jwt.encode(
        {
            "sub": str(row["id_usuario"]),
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=minutes),
            "iss": current_app.config["JWT_ISSUER"],
            "aud": current_app.config["JWT_AUDIENCE"],
            "type": "access",
        },
        current_app.config["SECRET_KEY"],
        algorithm="HS256",
    )

    return jsonify(
        access_token=token,
        token_type="Bearer",
        expires_in=minutes * 60,
        usuario=get_user(row["id_usuario"]),
    )


@bp.get("/me")
@jwt_required
def me():
    return jsonify(usuario=g.current_user)


@bp.get("/admin-check")
@roles_required("ADMIN")
def admin_check():
    return jsonify(message="Acceso administrativo autorizado.")


@bp.get("/roles")
@roles_required("ADMIN")
def list_roles():
    return jsonify(
        roles=fetch_all("SELECT id_rol, nombre FROM rol ORDER BY nombre")
    )


@bp.put("/users/<int:user_id>/roles")
@roles_required("ADMIN")
def assign_roles(user_id):
    data = body({"roles"})
    names = data.get("roles")

    if (
        not isinstance(names, list)
        or not names
        or len(names) > 6
        or any(not isinstance(name, str) for name in names)
    ):
        raise APIError("roles debe ser una lista de nombres de roles.")

    names = sorted(set(names))

    if user_id == g.current_user["id_usuario"] and "ADMIN" not in names:
        raise APIError("No puedes quitarte tu propio rol ADMIN.", 409)

    with transaction() as cursor:
        cursor.execute(
            "SELECT id_usuario FROM usuario WHERE id_usuario = %s "
            "FOR UPDATE",
            (user_id,),
        )

        if cursor.fetchone() is None:
            raise APIError("Usuario no encontrado.", 404)

        placeholders = ", ".join(["%s"] * len(names))

        cursor.execute(
            f"SELECT id_rol FROM rol WHERE nombre IN ({placeholders})",
            tuple(names),
        )
        roles = cursor.fetchall()

        if len(roles) != len(names):
            raise APIError("Uno o más roles no existen.")

        cursor.execute(
            "DELETE FROM usuario_rol WHERE id_usuario = %s",
            (user_id,),
        )

        cursor.executemany(
            "INSERT INTO usuario_rol (id_usuario, id_rol) "
            "VALUES (%s, %s)",
            [(user_id, role["id_rol"]) for role in roles],
        )

    return jsonify(usuario=get_user(user_id))


def init_app(app):
    @app.cli.command("create-admin")
    @click.option("--email", prompt="Email")
    @click.option("--nombre", prompt="Nombre")
    @click.option("--apellido", prompt="Apellido")
    @click.option(
        "--password",
        prompt="Contraseña",
        hide_input=True,
        confirmation_prompt=True,
    )
    def create_admin(email, nombre, apellido, password):
        try:
            user = create_user(
                {
                    "nombre": nombre,
                    "apellido": apellido,
                    "email": email,
                    "password": password,
                },
                "ADMIN",
            )
        except APIError as error:
            raise click.ClickException(error.message) from error
        except pymysql.MySQLError as error:
            current_app.logger.exception(
                "Error al crear el administrador."
            )
            raise click.ClickException(
                "Comprueba MariaDB y los roles iniciales."
            ) from error

        click.echo(f"Administrador creado: {user['email']}")