"""Descarga del original de un documento citado.

Para cualquier usuario autenticado, pero solo a través de una conversación
propia que lo cite y con la misma política que el chat. Todo rechazo es
404: no se confirma la existencia del documento.
"""

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.modules.auth.infrastructure.http import CurrentUserDep
from app.modules.company_knowledge.infrastructure.extraction import PDF_MEDIA_TYPE
from app.modules.company_knowledge.infrastructure.http.dependencies import (
    DownloadUseCaseDep,
)

router = APIRouter(prefix="/company-documents", tags=["company-documents"])

_UNSAFE_FILENAME_CHARS = '\\/:*?"<>|\r\n'


def _safe_filename(name: str) -> str:
    cleaned = "".join("_" if ch in _UNSAFE_FILENAME_CHARS else ch for ch in name).strip()
    return cleaned or "documento"


@router.get("/{document_id}/file")
async def download_document(
    document_id: UUID,
    use_case: DownloadUseCaseDep,
    user: CurrentUserDep,
    conversation_id: UUID = Query(...),
) -> Response:
    document, content = await use_case.execute(document_id, conversation_id, user)
    # TXT y Markdown SIEMPRE como texto plano: nunca algo que el navegador
    # renderice como HTML.
    media_type = (
        PDF_MEDIA_TYPE if document.media_type == PDF_MEDIA_TYPE else "text/plain; charset=utf-8"
    )
    filename = quote(_safe_filename(document.original_filename))
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
