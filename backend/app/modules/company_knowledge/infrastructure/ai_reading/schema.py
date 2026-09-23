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

    offset = _relative_offset(
        [page.numero for page in transcription.paginas], first_page, last_page
    )
    pages: dict[int, AiPageContent] = {}
    for raw_page in transcription.paginas:
        number = raw_page.numero + offset
        if not first_page <= number <= last_page or number in pages:
            continue
        page = raw_page
        content = page.contenido.strip()
        pages[number] = AiPageContent(
            page_number=number,
            page_type=page.tipo,
            content=content,
            legible=page.legible and bool(content),
        )
    if not pages:
        raise AiReadingError(AiReadErrorCode.INVALID_JSON, retryable=True)
    return [pages[number] for number in sorted(pages)]


def _relative_offset(numbers: list[int], first_page: int, last_page: int) -> int:
    """Corrimiento cuando el modelo numeró las páginas desde 1 dentro del tramo.

    Medido con Gemini Flash-Lite en la segunda ronda del spike: en el tramo
    6-10 devolvió 1-5, aunque el mensaje pide la numeración del documento.
    Solo se corre si NINGUNA página cae en el rango y todas forman 1..N
    dentro del largo del tramo; si no, se deja como vino.
    """
    if first_page == 1 or not numbers:
        return 0
    if any(first_page <= n <= last_page for n in numbers):
        return 0
    distinct = sorted(set(numbers))
    if (
        distinct == list(range(1, len(distinct) + 1))
        and len(distinct) <= last_page - first_page + 1
    ):
        return first_page - 1
    return 0
