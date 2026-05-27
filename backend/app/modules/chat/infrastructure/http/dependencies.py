from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import get_agent_sessionmaker
from app.modules.chat.application.use_cases import SendMessageUseCase
from app.modules.chat.domain.interfaces import AssistantMessageWriter, LLMRunner
from app.modules.chat.infrastructure.llm.runner import ClaudeAgentRunner
from app.modules.chat.infrastructure.persistence import (
    SqlAlchemyAssistantMessageWriter,
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


def get_send_message_use_case(
    repository: ConversationRepositoryDep,
    runner: LLMRunnerDep,
    assistant_writer: AssistantMessageWriterDep,
) -> SendMessageUseCase:
    return SendMessageUseCase(repository, runner, assistant_writer)


SendMessageUseCaseDep = Annotated[
    SendMessageUseCase, Depends(get_send_message_use_case)
]
