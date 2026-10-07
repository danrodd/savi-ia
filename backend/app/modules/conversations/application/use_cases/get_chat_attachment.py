from uuid import UUID

from app.modules.conversations.domain.entities import ChatAttachment
from app.modules.conversations.domain.exceptions import ChatAttachmentNotFoundError
from app.modules.conversations.domain.interfaces import ChatAttachmentRepository
from app.modules.conversations.domain.value_objects import ConversationOwner


class GetChatAttachmentUseCase:
    def __init__(self, repository: ChatAttachmentRepository) -> None:
        self._repository = repository

    async def execute(
        self, attachment_id: UUID, *, owner: ConversationOwner
    ) -> tuple[ChatAttachment, bytes]:
        """Imagen y bytes, solo para su dueño.

        No existe y "no es tuya" dan el mismo 404: distinguirlos confirmaría
        ids ajenos. Solo el dueño (no hay lectura de adjuntos ajenos ni para
        administradores: no existe ese concepto para las conversaciones)."""
        attachment = await self._repository.get(attachment_id)
        if attachment is None or not owner.owns(
            attachment.user_id, attachment.owner_erp_database_id
        ):
            raise ChatAttachmentNotFoundError
        content = await self._repository.get_content(attachment_id)
        if content is None:
            raise ChatAttachmentNotFoundError
        return attachment, content
