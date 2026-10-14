"""CSV del feedback para abrir directo en Excel (configuración regional es-CO).

- UTF-8 con BOM: sin él Excel lee las tildes como basura.
- Separador `;`: con la coma como separador decimal de Colombia, Excel
  espera `;` y mete todo en una sola columna si encuentra comas.
- Celdas que empiezan con `= + - @` se prefijan con una comilla simple
  (inyección de fórmulas: la pregunta del usuario es texto libre).
"""

import csv
import io
from collections.abc import Sequence

from app.modules.feedback.domain.value_objects import FeedbackReportItem

CSV_DELIMITER = ";"
_BOM = "﻿"
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

CSV_HEADERS = (
    "Fecha",
    "Usuario",
    "Nombre",
    "Calificación",
    "Motivo",
    "Comentario",
    "Pregunta",
    "Respuesta",
    "Proveedor",
    "Modelo",
    "Costo USD",
    "Herramientas",
    "Base",
    "Conversación",
    "Mensaje",
)

_RATING_LABEL = {"up": "Me sirvió", "down": "No me sirvió"}
_REASON_LABEL = {
    "dato_incorrecto": "El dato es incorrecto",
    "no_entendio": "No entendió mi pregunta",
    "incompleta": "Está incompleta",
    "muy_lenta": "Tardó demasiado",
    "otra": "Otra cosa",
}


def _safe(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_FORMULA_PREFIXES) else text


def build_feedback_csv(items: Sequence[FeedbackReportItem]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=CSV_DELIMITER, lineterminator="\r\n")
    writer.writerow(CSV_HEADERS)
    for item in items:
        writer.writerow(
            [
                _safe(item.created_at.isoformat(timespec="seconds")),
                _safe(item.user_login),
                _safe(item.user_name),
                _safe(_RATING_LABEL.get(item.rating.value, item.rating.value)),
                _safe(_REASON_LABEL.get(item.reason.value, "") if item.reason else ""),
                _safe(item.comment),
                _safe(item.question),
                _safe(item.answer),
                _safe(item.provider),
                _safe(item.model),
                _safe("" if item.cost_usd is None else f"{item.cost_usd:.6f}"),
                _safe(", ".join(item.tools)),
                _safe(item.database_code),
                _safe(item.conversation_id),
                _safe(item.message_id),
            ]
        )
    return (_BOM + buffer.getvalue()).encode("utf-8")
