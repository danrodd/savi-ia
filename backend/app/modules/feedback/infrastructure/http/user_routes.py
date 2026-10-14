"""Calificación 👍/👎 de las respuestas, por el propio usuario."""

from uuid import UUID

from fastapi import APIRouter, status

from app.modules.auth.infrastructure.http import CurrentUserDep
from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.feedback.application.requests import SetFeedbackRequest
from app.modules.feedback.application.responses import FeedbackResponse
from app.modules.feedback.infrastructure.http.dependencies import (
    ClearMessageFeedbackUseCaseDep,
    SetMessageFeedbackUseCaseDep,
    SettingsDep,
)
from app.shared.rate_limit import enforce_feedback_limits

router = APIRouter(prefix="/conversations", tags=["feedback"])


def _owner(user: CurrentUserDep) -> ConversationOwner:
    assert user.erp_database_id is not None  # noqa: S101 — el token no decodifica sin base
    return ConversationOwner(user_id=user.id, erp_database_id=user.erp_database_id)


@router.put(
    "/{conversation_id}/messages/{message_id}/feedback",
    response_model=FeedbackResponse,
)
async def set_feedback(
    conversation_id: UUID,
    message_id: UUID,
    request: SetFeedbackRequest,
    use_case: SetMessageFeedbackUseCaseDep,
    user: CurrentUserDep,
    settings: SettingsDep,
) -> FeedbackResponse:
    """Califica una respuesta vigente del asistente. Reemplaza la anterior.

    404 si el mensaje no es de una conversación del usuario; 422 si no es
    una respuesta del asistente, está reemplazada o el motivo viene con 👍.
    """
    enforce_feedback_limits(settings, user)
    feedback = await use_case.execute(
        conversation_id=conversation_id,
        message_id=message_id,
        owner=_owner(user),
        user_login=user.login,
        user_name=user.full_name,
        rating=request.rating,
        reason=request.reason,
        comment=request.comment,
    )
    return FeedbackResponse.from_entity(feedback)


@router.delete(
    "/{conversation_id}/messages/{message_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def clear_feedback(
    conversation_id: UUID,
    message_id: UUID,
    use_case: ClearMessageFeedbackUseCaseDep,
    user: CurrentUserDep,
) -> None:
    """Quita la calificación propia. Idempotente (204 aunque no hubiera)."""
    await use_case.execute(
        conversation_id=conversation_id, message_id=message_id, owner=_owner(user)
    )
