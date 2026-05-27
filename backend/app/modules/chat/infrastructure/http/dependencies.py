from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.modules.chat.application.use_cases import SendMessageUseCase
from app.modules.chat.domain.interfaces import LLMRunner
from app.modules.chat.infrastructure.llm.runner import ClaudeAgentRunner
from app.modules.conversations.infrastructure.http.dependencies import (
    ConversationRepositoryDep,
)


def get_settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_llm_runner(settings: SettingsDep) -> LLMRunner:
    return ClaudeAgentRunner(settings)


LLMRunnerDep = Annotated[LLMRunner, Depends(get_llm_runner)]


def get_send_message_use_case(
    repository: ConversationRepositoryDep,
    runner: LLMRunnerDep,
) -> SendMessageUseCase:
    return SendMessageUseCase(repository, runner)


SendMessageUseCaseDep = Annotated[
    SendMessageUseCase, Depends(get_send_message_use_case)
]
