from datetime import datetime

from flask import Blueprint, g, jsonify

from .auth import roles_required
from .db import fetch_all, fetch_one, transaction
from .errors import APIError
from .utils import body, text

bp = Blueprint("transparency", __name__, url_prefix="/api")


@bp.get("/transparency")
def list_documents():
    return jsonify(documentos=fetch_all(
        "SELECT id_documento, titulo, periodo, archivo_url, fecha_publicacion "
        "FROM documento_transparencia ORDER BY periodo DESC LIMIT 120"
    ))


@bp.post("/transparency")
@roles_required("ADMIN", "COOPERADORA")
def create_document():
    data = body({"titulo", "periodo", "archivo_url"})
    title = text(data.get("titulo"), "titulo", 200)
    url = text(data.get("archivo_url"), "archivo_url", 500)

    if not url.startswith(("http://", "https://")):
        raise APIError("archivo_url debe empezar con http:// o https://.")

    try:
        period = datetime.strptime(data.get("periodo"), "%Y-%m").date()
    except (ValueError, TypeError):
        raise APIError("periodo debe tener formato AAAA-MM.")

    with transaction() as cursor:
        cursor.execute(
            "INSERT INTO documento_transparencia "
            "(id_usuario, titulo, periodo, archivo_url) VALUES (%s, %s, %s, %s)",
            (g.current_user["id_usuario"], title, period, url),
        )
        doc_id = cursor.lastrowid

    return jsonify(id_documento=doc_id), 201