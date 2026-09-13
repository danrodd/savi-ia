from uuid import UUID

from app.modules.conversations.domain.exceptions import ConversationNotFoundError
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.domain.value_objects import ConversationOwner


class DeleteConversationUseCase:
    """Soft delete idempotente de una conversación.

    - Si la conversación existe (esté ya eliminada o no) y el caller es
      el dueño: éxito silencioso. Repetir `DELETE` sobre la misma
      conversación es seguro.
    - Si no existe o no pertenece al caller: `ConversationNotFoundError`
      → handler global emite 404 (no 403 para no filtrar existencia).

    No interfiere con turnos en curso: los writers del módulo `chat`
    operan con sessionmakers independientes y siguen insertando vía la
    FK `conversations.id`. Esos mensajes quedan asociados a la
    conversación invisible al usuario, que es justo lo esperado del
    soft delete (preserva trazabilidad sin exponer la data).
    """

    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        conversation_id: UUID,
        *,
        expected_owner: ConversationOwner | None = None,
    ) -> None:
        if expected_owner is not None:
            # Validamos ownership antes del soft delete: si no es del
            # caller, 404 (no exponer la existencia de la conversación).
            conversation = await self._repository.get_by_id(conversation_id)
            if (
                conversation is None
                or conversation.is_deleted
                or not expected_owner.owns(
                    conversation.user_id, conversation.erp_database_id
                )
            ):
                raise ConversationNotFoundError(conversation_id)
        existed = await self._repository.soft_delete(conversation_id)
        if not existed:
            raise ConversationNotFoundError(conversation_id)
