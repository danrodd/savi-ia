from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database.session import AgentSessionDep
from app.modules.conversations.application.use_cases import (
    CreateConversationUseCase,
    DeleteConversationUseCase,
    GetChatAttachmentUseCase,
    GetConversationWithMessagesUseCase,
    ListConversationsUseCase,
    RenameConversationUseCase,
    UploadChatAttachmentUseCase,
)
from app.modules.conversations.domain.interfaces import (
    ChatAttachmentRepository,
    ConversationRepository,
)
from app.modules.conversations.infrastructure.imaging import PillowImageProcessor
from app.modules.conversations.infrastructure.persistence.repositories import (
    SqlAlchemyChatAttachmentRepository,
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


def get_delete_conversation_use_case(
    repository: ConversationRepositoryDep,
) -> DeleteConversationUseCase:
    return DeleteConversationUseCase(repository)


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
DeleteConversationUseCaseDep = Annotated[
    DeleteConversationUseCase, Depends(get_delete_conversation_use_case)
]


def get_chat_attachment_repository(session: AgentSessionDep) -> ChatAttachmentRepository:
    return SqlAlchemyChatAttachmentRepository(session)


ChatAttachmentRepositoryDep = Annotated[
    ChatAttachmentRepository, Depends(get_chat_attachment_repository)
]


def _settings() -> Settings:
    return get_settings()


def get_upload_chat_attachment_use_case(
    repository: ChatAttachmentRepositoryDep,
) -> UploadChatAttachmentUseCase:
    return UploadChatAttachmentUseCase(repository, PillowImageProcessor(), _settings())


def get_get_chat_attachment_use_case(
    repository: ChatAttachmentRepositoryDep,
) -> GetChatAttachmentUseCase:
    return GetChatAttachmentUseCase(repository)


UploadChatAttachmentUseCaseDep = Annotated[
    UploadChatAttachmentUseCase, Depends(get_upload_chat_attachment_use_case)
]
GetChatAttachmentUseCaseDep = Annotated[
    GetChatAttachmentUseCase, Depends(get_get_chat_attachment_use_case)
]
