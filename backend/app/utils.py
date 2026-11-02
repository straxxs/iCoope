from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import request

from .errors import APIError


def body(allowed=None):
    if not request.is_json:
        raise APIError("Envía Content-Type: application/json.", 415)

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        raise APIError("El cuerpo debe ser un objeto JSON.")

    if allowed is not None and set(data) - set(allowed):
        raise APIError("Se recibieron campos no permitidos.")

    return data


def text(value, field, maximum, optional=False):
    if optional and value is None:
        return None

    if not isinstance(value, str):
        raise APIError(f"'{field}' debe ser texto.")

    value = value.strip()

    if not value or len(value) > maximum:
        raise APIError(
            f"'{field}' debe tener entre 1 y {maximum} caracteres."
        )

    return value


def integer(value, field, minimum=1, maximum=2147483647):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise APIError(
            f"'{field}' debe ser un entero entre "
            f"{minimum} y {maximum}."
        )

    return value


def boolean(value, field):
    if not isinstance(value, bool):
        raise APIError(f"'{field}' debe ser true o false.")

    return value


def money(value, field="precio"):
    if isinstance(value, bool) or not isinstance(
        value, (str, int, float, Decimal)
    ):
        raise APIError(f"'{field}' no es un importe válido.")

    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise APIError(f"'{field}' no es un importe válido.")

    if not amount.is_finite():
        raise APIError(f"'{field}' no es un importe válido.")

    if not Decimal("0") <= amount <= Decimal("99999999.99"):
        raise APIError(f"'{field}' está fuera del rango permitido.")

    if amount != amount.quantize(Decimal("0.01")):
        raise APIError(f"'{field}' admite hasta dos decimales.")

    return amount.quantize(Decimal("0.01"))


def date_time(value, field):
    if not isinstance(value, str):
        raise APIError(
            f"'{field}' debe ser una fecha ISO, "
            "por ejemplo 2026-11-20T18:00:00."
        )

    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise APIError(f"'{field}' no es una fecha válida.")

    # MariaDB DATETIME no almacena zona horaria.
    if result.tzinfo is not None:
        raise APIError(
            f"'{field}' debe enviarse sin zona horaria."
        )

    if not 1000 <= result.year <= 9999:
        raise APIError(f"'{field}' está fuera del rango de MariaDB.")

    return result


def pagination():
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        raise APIError("La paginación debe contener enteros.")

    if page < 1 or not 1 <= per_page <= 100:
        raise APIError(
            "page debe ser mayor que cero y per_page entre 1 y 100."
        )

    return page, per_page, (page - 1) * per_page


def require_row(row, message="Recurso no encontrado."):
    if row is None:
        raise APIError(message, 404)

    return row