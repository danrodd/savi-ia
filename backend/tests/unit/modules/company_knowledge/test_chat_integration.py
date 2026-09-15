"""Documentos en el turno del chat: fuentes, persistencia, runners y tool."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app.infrastructure.config.settings import Settings
from app.modules.chat.application.requests import ChatAction
from app.modules.chat.application.use_cases import ChatTurnUseCase
from app.modules.chat.domain.entities import (
    ChatEvent,
    DoneEvent,
    SourcesEvent,
    TextDeltaEvent,
)
from app.modules.chat.domain.interfaces import (
    ActiveProvider,
    AssistantMessageWriter,
    ConversationTitleUpdater,
    LLMRunner,
)
from app.modules.chat.infrastructure.llm.claude import runner as claude_runner
from app.modules.chat.infrastructure.llm.gemini import runner as gemini_runner
from app.modules.chat.infrastructure.llm.openai import runner as openai_runner
from app.modules.chat.infrastructure.llm.tools.knowledge import (
    KNOWLEDGE_TIPOS,
    build_consultar_conocimiento_impl,
)
from app.modules.chat.infrastructure.llm.tools.schemas import CONSULTAR_CONOCIMIENTO_SCHEMA
from app.modules.company_knowledge.domain.services import (
    CitedChunk,
    DocumentAccessContext,
    TurnDocumentContext,
)
from app.modules.conversations.domain.entities import Conversation, Message
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.knowledge.infrastructure.static_catalog import load_static_catalog

DOC_ID = uuid4()


def _context() -> TurnDocumentContext:
    context = TurnDocumentContext(access=DocumentAccessContext(uuid4(), frozenset(), False, False))
    context.citations.register(CitedChunk(DOC_ID, 2, "Manual de caja", 0, 3, 4))
    return context


class _Repo:
    def __init__(self) -> None:
        self.conversation = Conversation(title="Nueva conversación")

    async def get_by_id(self, conversation_id: UUID) -> Conversation:
        return self.conversation

    async def list_messages(self, conversation_id: UUID, **_: Any) -> list[Message]:
        return []

    async def add_message(self, message: Message) -> Message:
        return message


class _Writer:
    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def write(self, message: Message, *, supersedes_id: UUID | None) -> None:
        self.messages.append(message)


class _Titles:
    async def update_from_user(self, conversation_id: UUID, text: str) -> str | None:
        return None

    async def update_from_turn(
        self, conversation_id: UUID, user: str, assistant: str
    ) -> str | None:
        return None


class _Runner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.received: TurnDocumentContext | None = None

    async def stream_turn(self, prompt: str, **kwargs: Any) -> AsyncIterator[ChatEvent]:
        self.received = kwargs.get("document_context")
        yield TextDeltaEvent(text=self.text)
        yield DoneEvent()


async def _run(
    text: str, context: TurnDocumentContext | None
) -> tuple[list[ChatEvent], _Writer, _Runner]:
    runner, writer = _Runner(text), _Writer()
    use_case = ChatTurnUseCase(
        cast(ConversationRepository, _Repo()),
        cast(LLMRunner, runner),
        cast(AssistantMessageWriter, writer),
        cast(ConversationTitleUpdater, _Titles()),
        Settings(title_phase2_timeout_s=0.01),
    )
    events = [
        event
        async for event in use_case.execute(
            uuid4(), ChatAction.SEND, "¿tope de descuento?", document_context=context
        )
    ]
    await asyncio.sleep(0.05)  # el writer corre en una tarea independiente
    return events, writer, runner


async def test_sources_event_arrives_right_before_done_and_is_persisted() -> None:
    context = _context()
    events, writer, runner = await _run(
        "Lo autoriza el supervisor [D1]. Dato inventado [D9].", context
    )

    kinds = [type(event).__name__ for event in events]
    assert kinds.index("SourcesEvent") == kinds.index("DoneEvent") - 1
    sources_event = next(e for e in events if isinstance(e, SourcesEvent))
    assert sources_event.sources == [
        {
            "ref": "D1",
            "refs": ["D1"],
            "document_id": str(DOC_ID),
            "version": 2,
            "title": "Manual de caja",
            "pages": "3-4",
        }
    ]
    assert runner.received is context
    assert [s.document_id for s in writer.messages[0].sources] == [DOC_ID]


async def test_no_valid_references_means_no_sources_event() -> None:
    events, writer, _ = await _run("Respuesta sin citas válidas [D5].", _context())
    assert not any(isinstance(event, SourcesEvent) for event in events)
    assert writer.messages[0].sources == []


async def test_turn_without_document_context_still_works() -> None:
    events, writer, _ = await _run("Hola [D1].", None)
    assert isinstance(events[-1], DoneEvent)
    assert writer.messages[0].sources == []


# ── Los tres runners pasan el contexto a las tools ───────────────────────


class _CapturedError(Exception):
    def __init__(self, kwargs: dict[str, Any]) -> None:
        super().__init__("captured")
        self.kwargs = kwargs


def _capture(**kwargs: Any) -> list[Any]:
    raise _CapturedError(kwargs)


def _provider(kind: str) -> ActiveProvider:
    return ActiveProvider(
        kind=kind, chat_model="m", title_model="t", credential_kind="api_key", credential="k"
    )


@pytest.mark.parametrize(
    ("module", "factory"),
    [
        (claude_runner, lambda: claude_runner.ClaudeAgentRunner(Settings(), _provider("claude"))),
        (
            gemini_runner,
            lambda: gemini_runner.GeminiRunner(
                Settings(), _provider("gemini"), client=cast(Any, object())
            ),
        ),
        (
            openai_runner,
            lambda: openai_runner.OpenAIRunner(
                Settings(), _provider("openai"), client=cast(Any, object())
            ),
        ),
    ],
    ids=["claude", "gemini", "openai"],
)
async def test_every_runner_passes_document_context_to_tools(
    module: Any, factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "build_savi_tools", _capture)
    context = _context()
    with pytest.raises(_CapturedError) as captured:
        async for _ in factory().stream_turn("hola", document_context=context):
            pass
    assert captured.value.kwargs["document_context"] is context


# ── Dispatcher ───────────────────────────────────────────────────────────


def test_documentos_is_a_tipo_not_a_new_tool() -> None:
    assert "documentos" in KNOWLEDGE_TIPOS
    assert "documentos" in CONSULTAR_CONOCIMIENTO_SCHEMA["properties"]["tipo"]["enum"]


async def test_documentos_without_index_returns_a_note_not_an_error(tmp_path: Any) -> None:
    impl = build_consultar_conocimiento_impl(load_static_catalog(tmp_path), None, None)
    result = await impl({"tipo": "documentos", "consulta": "politica"})
    assert result["matches"] == [] and "error" not in result
