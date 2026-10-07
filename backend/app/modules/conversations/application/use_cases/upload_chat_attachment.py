import asyncio
import re
from datetime import UTC, datetime, timedelta

from app.infrastructure.config import Settings
from app.modules.conversations.domain.entities import ChatAttachment
from app.modules.conversations.domain.exceptions import (
    ChatAttachmentTooLargeError,
    InvalidChatAttachmentError,
)
from app.modules.conversations.domain.interfaces import ChatAttachmentRepository, ImageProcessor
from app.modules.conversations.domain.value_objects import ConversationOwner

# Una imagen subida y nunca enviada se descarta pasado este tiempo.
UNLINKED_TTL = timedelta(hours=24)

_MAX_FILENAME_LENGTH = 255
_DEFAULT_FILENAME = "imagen"
_UNSAFE_CHARS = re.compile(r"[^\w .()\-]+", re.UNICODE)


def sanitize_attachment_filename(raw: str | None) -> str:
    """Nombre seguro para guardar y mostrar.

    Descarta el directorio (el cliente puede mandar una ruta completa),
    caracteres de control y todo lo que no sea letra, número, espacio,
    punto, guion o paréntesis. El nombre viaja luego en el texto que ve el
    modelo, así que también se acota el vocabulario por esa vía.
    """
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = _UNSAFE_CHARS.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    name = name[:_MAX_FILENAME_LENGTH].strip(" .")
    return name or _DEFAULT_FILENAME


class UploadChatAttachmentUseCase:
    def __init__(
        self,
        repository: ChatAttachmentRepository,
        processor: ImageProcessor,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._processor = processor
        self._settings = settings

    async def execute(
        self, *, owner: ConversationOwner, filename: str | None, content: bytes
    ) -> ChatAttachment:
        limit_mb = self._settings.chat_image_max_mb
        if len(content) > limit_mb * 1024 * 1024:
            raise ChatAttachmentTooLargeError(limit_mb)
        if not content:
            raise InvalidChatAttachmentError("El archivo está vacío.")

        # Pillow es CPU puro: en un hilo para no frenar el loop del servidor.
        processed = await asyncio.to_thread(
            self._processor.process,
            content,
            max_side_px=self._settings.chat_image_max_side_px,
        )

        # Limpieza oportunista de lo que este usuario subió y nunca envió.
        await self._repository.delete_stale_unlinked(owner, datetime.now(UTC) - UNLINKED_TTL)

        attachment = ChatAttachment(
            user_id=owner.user_id,
            owner_erp_database_id=owner.erp_database_id,
            mime=processed.mime,
            filename=sanitize_attachment_filename(filename),
            size_bytes=len(processed.content),
            width=processed.width,
            height=processed.height,
        )
        return await self._repository.add(attachment, processed.content)
