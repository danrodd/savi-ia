"""Imágenes adjuntas al chat: subida y descarga.

Subir y enviar son dos pasos: `POST /chat/attachments` devuelve un id y el
mensaje de `POST /chat` lo referencia en `attachment_ids`.
"""

from uuid import UUID

from fastapi import APIRouter, File, Request, Response, UploadFile, status

from app.infrastructure.config import get_settings
from app.modules.auth.infrastructure.http import CurrentUserDep
from app.modules.conversations.application.responses import ChatAttachmentResponse
from app.modules.conversations.domain.exceptions import ChatAttachmentTooLargeError
from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.conversations.infrastructure.http.dependencies import (
    GetChatAttachmentUseCaseDep,
    UploadChatAttachmentUseCaseDep,
)
from app.shared.rate_limit import enforce_chat_attachment_limits

router = APIRouter(prefix="/chat/attachments", tags=["chat"])

_READ_BLOCK = 1024 * 1024
# Holgura del multipart (cabeceras y límites) sobre el peso del archivo.
_MULTIPART_OVERHEAD = 64 * 1024


def _owner(user: CurrentUserDep) -> ConversationOwner:
    assert user.erp_database_id is not None  # noqa: S101 — el token no decodifica sin base
    return ConversationOwner(user_id=user.id, erp_database_id=user.erp_database_id)


def _reject_oversized_body(request: Request, limit_mb: int) -> None:
    """Corta por `Content-Length` antes de leer el cuerpo; la lectura por
    bloques cubre un `Content-Length` ausente o falso."""
    declared = request.headers.get("content-length")
    limit = limit_mb * 1024 * 1024 + _MULTIPART_OVERHEAD
    if declared and declared.isdigit() and int(declared) > limit:
        raise ChatAttachmentTooLargeError(limit_mb)


async def _read_limited(file: UploadFile, limit_mb: int) -> bytes:
    limit = limit_mb * 1024 * 1024
    buffer = bytearray()
    while block := await file.read(_READ_BLOCK):
        buffer.extend(block)
        if len(buffer) > limit:
            raise ChatAttachmentTooLargeError(limit_mb)
    return bytes(buffer)


@router.post("", response_model=ChatAttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    request: Request,
    use_case: UploadChatAttachmentUseCaseDep,
    user: CurrentUserDep,
    file: UploadFile = File(...),
) -> ChatAttachmentResponse:
    settings = get_settings()
    # Antes de leer el cuerpo: decodificar imágenes es trabajo caro.
    enforce_chat_attachment_limits(settings, user)
    _reject_oversized_body(request, settings.chat_image_max_mb)
    content = await _read_limited(file, settings.chat_image_max_mb)
    attachment = await use_case.execute(owner=_owner(user), filename=file.filename, content=content)
    return ChatAttachmentResponse.from_entity(attachment)


@router.get("/{attachment_id}")
async def get_attachment(
    attachment_id: UUID,
    use_case: GetChatAttachmentUseCaseDep,
    user: CurrentUserDep,
) -> Response:
    """Bytes de la imagen. 404 si no existe o no es del usuario."""
    attachment, content = await use_case.execute(attachment_id, owner=_owner(user))
    return Response(
        content=content,
        media_type=attachment.mime,
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )
