from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import get_agent_sessionmaker
from app.modules.chat.application.use_cases import SendMessageUseCase
from app.modules.chat.domain.interfaces import (
    AssistantMessageWriter,
    ConversationTitleUpdater,
    LLMRunner,
)
from app.modules.chat.infrastructure.llm.runner import ClaudeAgentRunner
from app.modules.chat.infrastructure.persistence import (
    SqlAlchemyAssistantMessageWriter,
    SqlAlchemyConversationTitleUpdater,
)
from app.modules.conversations.infrastructure.http.dependencies import (
    ConversationRepositoryDep,
)


def get_settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_llm_runner(settings: SettingsDep) -> LLMRunner:
    return ClaudeAgentRunner(settings)


LLMRunnerDep = Annotated[LLMRunner, Depends(get_llm_runner)]


def get_assistant_message_writer() -> AssistantMessageWriter:
    return SqlAlchemyAssistantMessageWriter(get_agent_sessionmaker())


AssistantMessageWriterDep = Annotated[
    AssistantMessageWriter, Depends(get_assistant_message_writer)
]


def get_conversation_title_updater(
    settings: SettingsDep,
) -> ConversationTitleUpdater:
    return SqlAlchemyConversationTitleUpdater(
        sessionmaker=get_agent_sessionmaker(),
        settings=settings,
    )


ConversationTitleUpdaterDep = Annotated[
    ConversationTitleUpdater, Depends(get_conversation_title_updater)
]


def get_send_message_use_case(
    repository: ConversationRepositoryDep,
    runner: LLMRunnerDep,
    assistant_writer: AssistantMessageWriterDep,
    title_updater: ConversationTitleUpdaterDep,
    settings: SettingsDep,
) -> SendMessageUseCase:
    return SendMessageUseCase(
        repository=repository,
        runner=runner,
        assistant_writer=assistant_writer,
        title_updater=title_updater,
        settings=settings,
    )


SendMessageUseCaseDep = Annotated[
    SendMessageUseCase, Depends(get_send_message_use_case)
]
