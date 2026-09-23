"""Esquema de la respuesta de transcripción y su validación (§6.2).

El mismo esquema va a los tres proveedores como salida estructurada. Cumple
el modo estricto de OpenAI: `additionalProperties: false` y todos los campos
requeridos. La respuesta se valida siempre acá, aunque el proveedor diga que
respetó el esquema.
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.modules.company_knowledge.domain.entities.page_reading import AiPageContent
from app.modules.company_knowledge.domain.exceptions import AiReadingError
from app.modules.company_knowledge.domain.value_objects import AiReadErrorCode

PAGE_TYPES = ("texto", "tabla", "diagrama", "foto", "formulario", "mixto")

TRANSCRIPTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["paginas"],
    "properties": {
        "paginas": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["numero", "tipo", "contenido", "legible"],
                "properties": {
                    "numero": {"type": "integer"},
                    "tipo": {"type": "string", "enum": list(PAGE_TYPES)},
                    "contenido": {"type": "string"},
                    "legible": {"type": "boolean"},
                },
            },
        }
    },
}


class _Page(BaseModel):
    numero: int
    tipo: Literal["texto", "tabla", "diagrama", "foto", "formulario", "mixto"]
    contenido: str
    legible: bool


class _Transcription(BaseModel):
    paginas: list[_Page]


def parse_transcription(
    raw: str | dict[str, Any], first_page: int, last_page: int
) -> list[AiPageContent]:
    """Valida la respuesta y se queda con las páginas del tramo.

    Descarta números fuera de rango y repetidos (se queda con el primero):
    una página que falte se cubre después con el texto de `pypdf`.
    """
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        transcription = _Transcription.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise AiReadingError(AiReadErrorCode.INVALID_JSON, retryable=True) from exc

    pages: dict[int, AiPageContent] = {}
    for page in transcription.paginas:
        if not first_page <= page.numero <= last_page or page.numero in pages:
            continue
        content = page.contenido.strip()
        pages[page.numero] = AiPageContent(
            page_number=page.numero,
            page_type=page.tipo,
            content=content,
            legible=page.legible and bool(content),
        )
    if not pages:
        raise AiReadingError(AiReadErrorCode.INVALID_JSON, retryable=True)
    return [pages[number] for number in sorted(pages)]
