from uuid import UUID

from app.modules.conversations.domain.exceptions import ConversationNotFoundError
from app.modules.conversations.domain.interfaces import ConversationRepository


class DeleteConversationUseCase:
    """Soft delete idempotente de una conversación.

    - Si la conversación existe (esté ya eliminada o no): éxito silencioso.
      Repetir `DELETE` sobre la misma conversación es seguro.
    - Si no existe: `ConversationNotFoundError` → handler global emite 404.

    No interfiere con turnos en curso: los writers del módulo `chat`
    operan con sessionmakers independientes y siguen insertando vía la
    FK `conversations.id`. Esos mensajes quedan asociados a la
    conversación invisible al usuario, que es justo lo esperado del
    soft delete (preserva trazabilidad sin exponer la data).
    """

    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository

    async def execute(self, conversation_id: UUID) -> None:
        existed = await self._repository.soft_delete(conversation_id)
        if not existed:
            raise ConversationNotFoundError(conversation_id)
