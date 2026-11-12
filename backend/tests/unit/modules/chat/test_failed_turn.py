"""Un turno que falla queda guardado (P4 de los hallazgos de la primera demo).

En la demo, dos preguntas quedaron sin ninguna respuesta al recargar: el turno
fallaba antes del primer texto y no se guardaba nada. Ahora se guarda con su
categoría, el texto que vio el usuario y el código de soporte, y el turno
siguiente sabe que esa pregunta no se respondió.

Contra SQLite real con el repositorio que usa el endpoint; el runner es un doble.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.config import Settings
from app.infrastructure.database.base import Base
from app.modules.chat.application.requests import ChatAction
from app.modules.chat.application.use_cases import ChatTurnUseCase
from app.modules.chat.application.use_cases.chat_turn import (
    _format_history_block,  # pyright: ignore[reportPrivateUsage]
)
from app.modules.chat.domain.entities import (
    PROVIDER_BUSY_MESSAGE,
    ChatEvent,
    DoneEvent,
    ErrorCode,
    ErrorEvent,
    ImageInput,
    TextDeltaEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from app.modules.chat.domain.interfaces import (
    AssistantMessageWriter,
    ConversationTitleUpdater,
    LLMRunner,
)
from app.modules.chat.infrastructure.persistence import (
    ShortLivedConversationRepository,
    SqlAlchemyAssistantMessageWriter,
)
from app.modules.conversations.domain.entities import Conversation, Message, MessageRole
from app.modules.conversations.domain.value_objects import (
    ConversationOwner,
    MessageFinishReason,
)
from app.modules.conversations.infrastructure.persistence.repositories import (
    SqlAlchemyConversationRepository,
)
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel

_DB = UUID("22222222-2222-2222-2222-222222222222")
_OWNER = ConversationOwner(user_id=7, erp_database_id=_DB)


class _Runner:
    """Responde con la secuencia de eventos que le toque a cada turno."""

    def __init__(self, turns: list[list[ChatEvent] | Exception]) -> None:
        self.turns = turns
        self.prompts: list[str] = []

    async def stream_turn(
        self, prompt: str, *, images: Sequence[ImageInput] = (), **_: Any
    ) -> AsyncIterator[ChatEvent]:
        self.prompts.append(prompt)
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        for event in turn:
            yield event


class _Titles:
    async def update_from_user(self, conversation_id: UUID, text: str) -> str | None:
        return None

    async def update_from_turn(
        self, conversation_id: UUID, user: str, assistant: str
    ) -> str | None:
        return None


@pytest_asyncio.fixture
async def sm(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'turno.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        s.add(
            ErpDatabaseModel(
                id=_DB,
                code="DUENO",
                name="Cliente",
                host="localhost",
                port=5432,
                database="erp",
                username="postgres",
                password_encrypted="cifrado",
            )
        )
        await s.commit()
    yield factory
    await engine.dispose()


async def _conversation(sm: async_sessionmaker[AsyncSession]) -> UUID:
    async with sm() as session:
        saved = await SqlAlchemyConversationRepository(session).save(
            Conversation(id=uuid4(), user_id=7, erp_database_id=_DB, owner_erp_database_id=_DB)
        )
        await session.commit()
    return saved.id


async def _turn(
    sm: async_sessionmaker[AsyncSession], runner: _Runner, conversation_id: UUID, text: str
) -> tuple[list[ChatEvent], list[Message]]:
    repository = ShortLivedConversationRepository(sm)
    use_case = ChatTurnUseCase(
        repository,
        cast(LLMRunner, runner),
        cast(AssistantMessageWriter, SqlAlchemyAssistantMessageWriter(sm)),
        cast(ConversationTitleUpdater, _Titles()),
        Settings(title_phase2_timeout_s=0.01),
    )
    await use_case.validate(conversation_id, ChatAction.SEND, expected_owner=_OWNER)
    events = [e async for e in use_case.execute(conversation_id, ChatAction.SEND, text)]
    await asyncio.sleep(0.05)  # el writer del assistant corre en una tarea aparte
    return events, await repository.list_messages(conversation_id)


def _busy_after_two_queries() -> list[ChatEvent]:
    return [
        ToolUseEvent(id="t1", name="consultar_datos", input={}),
        ToolResultEvent(tool_use_id="t1", is_error=False),
        ToolUseEvent(id="t2", name="consultar_datos", input={}),
        ToolResultEvent(tool_use_id="t2", is_error=False),
        ErrorEvent(message=PROVIDER_BUSY_MESSAGE, code=ErrorCode.PROVIDER_BUSY),
    ]


async def test_a_turn_that_fails_before_any_text_is_saved(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    conversation_id = await _conversation(sm)

    events, messages = await _turn(
        sm, _Runner([_busy_after_two_queries()]), conversation_id, "Productos sin movimiento"
    )

    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert error.support_code is not None and len(error.support_code) == 8
    assistant = messages[-1]
    assert assistant.role == MessageRole.ASSISTANT
    assert assistant.content == ""
    assert assistant.finish_reason == MessageFinishReason.ERROR
    assert assistant.error_code == "provider_busy"
    assert assistant.error_message == PROVIDER_BUSY_MESSAGE
    assert assistant.support_code == error.support_code
    # Las consultas que alcanzó a hacer también quedan.
    assert [t.id for t in assistant.tool_invocations] == ["t1", "t2"]


async def test_the_next_turn_knows_the_previous_question_was_not_answered(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    conversation_id = await _conversation(sm)
    runner = _Runner([_busy_after_two_queries(), [TextDeltaEvent(text="Aquí están."), DoneEvent()]])

    await _turn(sm, runner, conversation_id, "Productos sin movimiento")
    await _turn(sm, runner, conversation_id, "¿Por qué?")

    assert "no se respondió" in runner.prompts[1]


async def test_an_unexpected_failure_ends_with_an_error_instead_of_cutting_the_stream(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    conversation_id = await _conversation(sm)

    events, messages = await _turn(sm, _Runner([RuntimeError("boom")]), conversation_id, "Hola")

    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert error.code is ErrorCode.INTERNAL
    assert "boom" not in error.message
    assert messages[-1].error_code == "internal_error"


def test_the_history_marks_a_failed_answer() -> None:
    failed = Message(
        role=MessageRole.ASSISTANT,
        content="",
        finish_reason=MessageFinishReason.ERROR,
    )
    block = _format_history_block([Message(role=MessageRole.USER, content="¿Stock?"), failed])

    assert "SAVI: [esta respuesta falló" in block
