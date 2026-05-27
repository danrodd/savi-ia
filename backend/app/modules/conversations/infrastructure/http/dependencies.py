from typing import Annotated

from fastapi import Depends

from app.infrastructure.database.session import AgentSessionDep
from app.modules.conversations.application.use_cases import (
    CreateConversationUseCase,
    GetConversationWithMessagesUseCase,
    ListConversationsUseCase,
    RenameConversationUseCase,
)
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.infrastructure.persistence.repositories import (
    SqlAlchemyConversationRepository,
)


def get_conversation_repository(session: AgentSessionDep) -> ConversationRepository:
    return SqlAlchemyConversationRepository(session)


ConversationRepositoryDep = Annotated[ConversationRepository, Depends(get_conversation_repository)]


def get_create_conversation_use_case(
    repository: ConversationRepositoryDep,
) -> CreateConversationUseCase:
    return CreateConversationUseCase(repository)


def get_list_conversations_use_case(
    repository: ConversationRepositoryDep,
) -> ListConversationsUseCase:
    return ListConversationsUseCase(repository)


def get_conversation_with_messages_use_case(
    repository: ConversationRepositoryDep,
) -> GetConversationWithMessagesUseCase:
    return GetConversationWithMessagesUseCase(repository)


def get_rename_conversation_use_case(
    repository: ConversationRepositoryDep,
) -> RenameConversationUseCase:
    return RenameConversationUseCase(repository)


CreateConversationUseCaseDep = Annotated[
    CreateConversationUseCase, Depends(get_create_conversation_use_case)
]
ListConversationsUseCaseDep = Annotated[
    ListConversationsUseCase, Depends(get_list_conversations_use_case)
]
GetConversationWithMessagesUseCaseDep = Annotated[
    GetConversationWithMessagesUseCase, Depends(get_conversation_with_messages_use_case)
]
RenameConversationUseCaseDep = Annotated[
    RenameConversationUseCase, Depends(get_rename_conversation_use_case)
]
