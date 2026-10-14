from uuid import UUID

from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.feedback.domain.entities import MessageFeedback
from app.modules.feedback.domain.exceptions import (
    FeedbackNotAllowedError,
    FeedbackTargetNotFoundError,
)
from app.modules.feedback.domain.interfaces import FeedbackRepository, FeedbackTarget
from app.modules.feedback.domain.value_objects import (
    COMMENT_MAX_LENGTH,
    FeedbackRating,
    FeedbackReason,
)


async def resolve_owned_target(
    repository: FeedbackRepository,
    *,
    conversation_id: UUID,
    message_id: UUID,
    owner: ConversationOwner,
) -> FeedbackTarget:
    """El mensaje, solo si es de una conversación vigente del usuario.

    Ajeno, inexistente o de una conversación borrada dan el mismo 404: no se
    confirma la existencia de mensajes de otros.
    """
    target = await repository.get_target(conversation_id, message_id)
    if (
        target is None
        or target.conversation_deleted
        or not owner.owns(target.conversation_user_id, target.conversation_owner_database_id)
    ):
        raise FeedbackTargetNotFoundError(message_id)
    return target


class SetMessageFeedbackUseCase:
    """Califica (o reemplaza la calificación de) una respuesta del asistente."""

    def __init__(self, repository: FeedbackRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        conversation_id: UUID,
        message_id: UUID,
        owner: ConversationOwner,
        user_login: str,
        user_name: str,
        rating: FeedbackRating,
        reason: FeedbackReason | None,
        comment: str | None,
    ) -> MessageFeedback:
        target = await resolve_owned_target(
            self._repository,
            conversation_id=conversation_id,
            message_id=message_id,
            owner=owner,
        )
        if target.role != "assistant":
            raise FeedbackNotAllowedError("Solo se pueden calificar las respuestas del asistente.")
        if target.is_superseded:
            raise FeedbackNotAllowedError(
                "Esa respuesta ya fue reemplazada: calificá la versión vigente."
            )
        if rating is FeedbackRating.UP and reason is not None:
            raise FeedbackNotAllowedError("El motivo solo se envía con una calificación negativa.")
        clean_comment = (comment or "").strip() or None
        if clean_comment is not None and len(clean_comment) > COMMENT_MAX_LENGTH:
            raise FeedbackNotAllowedError(
                f"El comentario no puede superar los {COMMENT_MAX_LENGTH} caracteres."
            )
        feedback = MessageFeedback(
            message_id=message_id,
            user_id=owner.user_id,
            owner_erp_database_id=owner.erp_database_id,
            rating=rating,
            reason=reason,
            comment=clean_comment,
            user_login=user_login.strip()[:50] or None,
            user_name=user_name.strip()[:200] or None,
        )
        return await self._repository.upsert(feedback)
