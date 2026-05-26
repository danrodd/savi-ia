from uuid import UUID

from fastapi import APIRouter, Query, status

from app.modules.conversations.application.dtos import CreateConversationDTO
from app.modules.conversations.application.requests import CreateConversationRequest
from app.modules.conversations.application.responses import (
    ConversationResponse,
    ConversationWithMessagesResponse,
)
from app.modules.conversations.infrastructure.http.dependencies import (
    CreateConversationUseCaseDep,
    GetConversationWithMessagesUseCaseDep,
    ListConversationsUseCaseDep,
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
) -> ConversationWithMessagesResponse:
    result = await use_case.execute(conversation_id)
    return ConversationWithMessagesResponse.from_dto(result)
