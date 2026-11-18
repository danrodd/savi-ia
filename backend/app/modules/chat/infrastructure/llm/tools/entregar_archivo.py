"""Tool `entregar_archivo`: el usuario pide un archivo y SAVI se lo entrega.

Dos tipos (ver `docs/plataforma/12-generacion-de-documentos.md`):

- `exportar`: un conjunto de resultados de esta conversación a Excel, PDF o CSV.
- `documento`: título y bloques validados (texto, listas, datos clave y tablas
  que referencian conjuntos) a PDF o Word.

El modelo describe; el servidor arma con plantillas fijas. El archivo queda
adjunto a la respuesta y solo lo descarga el dueño de la conversación.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from pydantic import ValidationError as SpecValidationError

from app.infrastructure.database import get_agent_sessionmaker
from app.modules.documents.application.document_spec import DocumentSpec
from app.modules.documents.application.file_use_cases import (
    BuildDocumentUseCase,
    ExportToFileUseCase,
    FileRequestError,
)
from app.modules.documents.domain.files import FileFormat
from app.modules.documents.infrastructure.branding import read_branding
from app.modules.documents.infrastructure.exporters import FileRenderer
from app.modules.documents.infrastructure.repository import (
    SqlAlchemyResultSetRepository,
    SqlAlchemyStoredFileRepository,
)

log = logging.getLogger(__name__)

ENTREGAR_ARCHIVO_DESCRIPTION = (
    "Genera un archivo para que el usuario lo descargue. Úsala cuando pida un "
    "Excel, PDF, CSV o Word, o un informe, listado o documento para bajar.\n\n"
    "- `tipo: 'exportar'`: una tabla de datos ya consultada, con TODAS sus filas. "
    "`formato`: xlsx, pdf o csv. `conjunto`: el identificador que te dio la consulta "
    "(si lo omites, se usa la última consulta de la conversación).\n"
    "- `tipo: 'documento'`: un informe con texto y tablas. `formato`: pdf o docx. "
    "`titulo` y `bloques`, cada bloque uno de: {tipo:'titulo2', texto}, "
    "{tipo:'parrafo', texto}, {tipo:'lista', items:[...]}, "
    "{tipo:'datos_clave', items:[[etiqueta, valor], ...]}, "
    "{tipo:'tabla', conjunto:'<id>', columnas:[...opcional]}, "
    "{tipo:'grafico', conjunto:'<id>', etiqueta:'<columna>', valor:'<columna numérica>', "
    "forma:'barras'|'torta'|'lineas', titulo:'...'}. Barras (por defecto) para "
    "comparar categorías: muestra los 15 mayores. Torta solo para partes de un total "
    "sin negativos: 7 porciones y el resto en 'Otros'. Líneas para la evolución en el "
    "tiempo: hasta 60 puntos, en el orden de la consulta (ordénala por fecha).\n\n"
    "Reglas: las tablas NO llevan filas, solo el identificador del conjunto; el "
    "servidor pone los datos. En el texto usa solo cifras que vengan de las consultas. "
    "Un documento sin tablas solo si el tema es del negocio (carta de cobro, acta). "
    "Después de generarlo, dile al usuario que el archivo está listo debajo de tu "
    "respuesta; no pegues su contenido."
)

ENTREGAR_ARCHIVO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tipo": {"type": "string", "enum": ["exportar", "documento"]},
        "formato": {"type": "string", "enum": ["xlsx", "pdf", "csv", "docx"]},
        "conjunto": {"type": "string", "description": "Identificador del conjunto (exportar)."},
        "titulo": {"type": "string", "description": "Título del documento."},
        "bloques": {
            "type": "array",
            "description": "Bloques del documento, en orden.",
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {
                        "type": "string",
                        "enum": ["titulo2", "parrafo", "lista", "datos_clave", "tabla", "grafico"],
                    },
                    "texto": {"type": "string"},
                    "items": {"type": "array", "items": {}},
                    "conjunto": {"type": "string"},
                    "columnas": {"type": "array", "items": {"type": "string"}},
                    "etiqueta": {"type": "string"},
                    "valor": {"type": "string"},
                    "forma": {"type": "string", "enum": ["barras", "torta", "lineas"]},
                    "titulo": {"type": "string"},
                },
                "required": ["tipo"],
            },
        },
    },
    "required": ["tipo", "formato"],
}


def _text(message: str, *, error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": error}


def build_entregar_archivo_impl(conversation_id: UUID | None, erp_database_id: UUID | None):
    async def impl(args: dict[str, Any]) -> dict[str, Any]:
        if conversation_id is None:
            return _text("No hay una conversación a la que adjuntar el archivo.", error=True)
        sessionmaker = get_agent_sessionmaker()
        result_sets = SqlAlchemyResultSetRepository(sessionmaker)
        files = SqlAlchemyStoredFileRepository(sessionmaker)
        renderer = FileRenderer()
        branding = await read_branding(erp_database_id)
        tipo = str(args.get("tipo", "")).strip().lower()
        try:
            if tipo == "exportar":
                raw_id = str(args.get("conjunto") or "").strip()
                try:
                    file_format = FileFormat(str(args.get("formato", "")).lower())
                    result_set_id = UUID(raw_id) if raw_id else None
                except ValueError:
                    return _text(
                        "Formato o identificador inválido: el formato es xlsx, pdf o csv y "
                        "el conjunto es el identificador que te dio la consulta.",
                        error=True,
                    )
                stored = await ExportToFileUseCase(result_sets, files, renderer).execute(
                    conversation_id, file_format, result_set_id, branding
                )
            elif tipo == "documento":
                try:
                    spec = DocumentSpec.model_validate(
                        {k: args.get(k) for k in ("formato", "titulo", "bloques")}
                    )
                except SpecValidationError as e:
                    problems = "; ".join(
                        f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                        for err in e.errors()[:5]
                    )
                    return _text(
                        f"La especificación del documento no es válida: {problems}", error=True
                    )
                stored = await BuildDocumentUseCase(result_sets, files, renderer).execute(
                    conversation_id, spec, branding
                )
            else:
                return _text("`tipo` tiene que ser 'exportar' o 'documento'.", error=True)
        except FileRequestError as e:
            return _text(str(e), error=True)
        size_kb = max(1, stored.size_bytes // 1024)
        return _text(
            f"Archivo listo: {stored.filename} ({size_kb} KB). Ya le aparece al usuario "
            "como adjunto debajo de tu respuesta, con el botón para descargarlo. Díselo en "
            "una frase; no pegues el contenido."
        )

    return impl
