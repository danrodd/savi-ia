from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import get_agent_sessionmaker
from app.modules.chat.application.use_cases import ChatTurnUseCase
from app.modules.chat.domain.interfaces import (
    AssistantMessageWriter,
    ConversationTitleUpdater,
    LLMRunner,
)
from app.modules.chat.infrastructure.llm.runner import ClaudeAgentRunner
from app.modules.chat.infrastructure.persistence import (
    ShortLivedConversationRepository,
    SqlAlchemyAssistantMessageWriter,
    SqlAlchemyConversationTitleUpdater,
)
from app.modules.conversations.domain.interfaces import ConversationRepository


def get_settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_llm_runner(settings: SettingsDep) -> LLMRunner:
    return ClaudeAgentRunner(settings)


LLMRunnerDep = Annotated[LLMRunner, Depends(get_llm_runner)]


def get_assistant_message_writer() -> AssistantMessageWriter:
    return SqlAlchemyAssistantMessageWriter(get_agent_sessionmaker())


AssistantMessageWriterDep = Annotated[AssistantMessageWriter, Depends(get_assistant_message_writer)]


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


def get_turn_conversation_repository() -> ConversationRepository:
    """Repositorio de transacciones cortas para el turno.

    NO se usa `ConversationRepositoryDep`, que va sobre la sesión del
    request: FastAPI cierra esa sesión recién cuando termina la respuesta,
    y en un `StreamingResponse` eso es después de todo el turno. El
    INSERT del mensaje del usuario quedaba sin commitear todo ese rato y,
    sobre SQLite —que admite un solo escritor— retenía el lock mientras
    el auto-título y la auditoría se colgaban esperándolo.
    """
    return ShortLivedConversationRepository(get_agent_sessionmaker())


TurnConversationRepositoryDep = Annotated[
    ConversationRepository, Depends(get_turn_conversation_repository)
]


def get_chat_turn_use_case(
    repository: TurnConversationRepositoryDep,
    runner: LLMRunnerDep,
    assistant_writer: AssistantMessageWriterDep,
    title_updater: ConversationTitleUpdaterDep,
    settings: SettingsDep,
) -> ChatTurnUseCase:
    return ChatTurnUseCase(
        repository=repository,
        runner=runner,
        assistant_writer=assistant_writer,
        title_updater=title_updater,
        settings=settings,
    )


ChatTurnUseCaseDep = Annotated[ChatTurnUseCase, Depends(get_chat_turn_use_case)]
