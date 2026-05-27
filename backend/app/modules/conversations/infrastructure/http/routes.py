from uuid import UUID

from fastapi import APIRouter, Query, status

from app.modules.conversations.application.dtos import CreateConversationDTO
from app.modules.conversations.application.requests import (
    CreateConversationRequest,
    RenameConversationRequest,
)
from app.modules.conversations.application.responses import (
    ConversationResponse,
    ConversationWithMessagesResponse,
)
from app.modules.conversations.infrastructure.http.dependencies import (
    CreateConversationUseCaseDep,
    DeleteConversationUseCaseDep,
    GetConversationWithMessagesUseCaseDep,
    ListConversationsUseCaseDep,
    RenameConversationUseCaseDep,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    request: CreateConversationRequest,
    use_case: CreateConversationUseCaseDep,
) -> ConversationResponse:
    dto = CreateConversationDTO(title=request.title, user_id=request.user_id)
    result = await use_case.execute(dto)
    return ConversationResponse.from_dto(result)


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    use_case: ListConversationsUseCaseDep,
    user_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ConversationResponse]:
    results = await use_case.execute(user_id, limit=limit, offset=offset)
    return [ConversationResponse.from_dto(r) for r in results]


@router.get("/{conversation_id}", response_model=ConversationWithMessagesResponse)
async def get_conversation(
    conversation_id: UUID,
    use_case: GetConversationWithMessagesUseCaseDep,
    include_superseded: bool = Query(
        default=False,
        description=(
            "Si true, incluye en `messages` las versiones anteriores de mensajes "
            "editados o regenerados (con `superseded_at`/`superseded_by_id` set). "
            "Default: solo el hilo activo."
        ),
    ),
) -> ConversationWithMessagesResponse:
    result = await use_case.execute(
        conversation_id, include_superseded=include_superseded
    )
    return ConversationWithMessagesResponse.from_dto(result)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: UUID,
    request: RenameConversationRequest,
    use_case: RenameConversationUseCaseDep,
) -> ConversationResponse:
    """Renombra la conversación y bloquea los autotítulos futuros
    (`title_locked=True`). Lo usa el botón de "Renombrar" del sidebar.
    """
    result = await use_case.execute(conversation_id, request.title)
    return ConversationResponse.from_dto(result)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    use_case: DeleteConversationUseCaseDep,
) -> None:
    """Soft delete idempotente: marca `deleted_at=now()` y deja de aparecer
    en listados / `GET /conversations/{id}`. Si ya estaba eliminada,
    devuelve 204 igual (idempotente). Si nunca existió, 404.

    No interrumpe turnos en curso: los writers independientes del módulo
    `chat` siguen insertando los mensajes pendientes contra la
    conversación, que quedan persistidos pero invisibles al usuario.
    """
    await use_case.execute(conversation_id)
