"""Use case del turno de chat.

Diseño:
- Persiste el mensaje del usuario inline contra la sesión del request.
- Acumula durante el stream: texto, tool_invocations (con su input y status
  final), usage y costo del DoneEvent, y un `finish_reason` que refleja
  cómo cerró el turno (complete/interrupted/error/truncated).
- En el `finally`, despacha la persistencia del mensaje del asistente como
  `asyncio.create_task` contra un writer con sesión independiente. Eso
  permite que la escritura sobreviva a la cancelación del cliente sin
  shielded waits ni perder el contenido parcial generado.
- La referencia fuerte de las tareas se mantiene en `_BG_TASKS` para que
  el GC no las recolecte antes de que terminen.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Coroutine
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.chat.domain.entities import (
    ChatEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from app.modules.chat.domain.interfaces import AssistantMessageWriter, LLMRunner
from app.modules.conversations.domain.entities import Message, MessageRole
from app.modules.conversations.domain.exceptions import ConversationNotFoundError
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.domain.value_objects import (
    MessageFinishReason,
    TokenUsage,
    ToolInvocation,
    ToolInvocationStatus,
)

log = logging.getLogger(__name__)

_HISTORY_TURNS = 20
_HISTORY_CHAR_LIMIT = 1500
_NEW_QUERY_MARKER = "=== Nueva consulta del usuario (responde esta) ==="
_TRUNCATION_MARKER = "Respuesta truncada por límite de tamaño"

_BG_TASKS: set[asyncio.Task[None]] = set()


def _spawn(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task


def _format_history_block(messages: list[Message]) -> str:
    if not messages:
        return ""
    recent = messages[-_HISTORY_TURNS:]
    lines = ["=== Historial de esta conversación ==="]
    for m in recent:
        who = "Usuario" if m.role == MessageRole.USER else "SAVI"
        body = m.content.strip()
        if len(body) > _HISTORY_CHAR_LIMIT:
            body = body[:_HISTORY_CHAR_LIMIT] + " …"
        if (
            m.role == MessageRole.ASSISTANT
            and m.finish_reason == MessageFinishReason.INTERRUPTED
        ):
            body += "\n\n[respuesta interrumpida por el usuario]"
        lines.append(f"{who}: {body}")
    lines.append(_NEW_QUERY_MARKER)
    return "\n\n".join(lines) + "\n\n"


class _TurnAccumulator:
    """Estado mutable durante el stream del turno."""

    def __init__(self) -> None:
        self.text_parts: list[str] = []
        self.tool_invocations: dict[str, ToolInvocation] = {}
        self.usage: TokenUsage | None = None
        self.cost_usd: Decimal | None = None
        self.finish_reason: MessageFinishReason = MessageFinishReason.COMPLETE

    def consume(self, event: ChatEvent) -> None:
        if isinstance(event, TextDeltaEvent):
            self.text_parts.append(event.text)
            if (
                self.finish_reason == MessageFinishReason.COMPLETE
                and _TRUNCATION_MARKER in event.text
            ):
                self.finish_reason = MessageFinishReason.TRUNCATED
        elif isinstance(event, ToolUseEvent):
            self.tool_invocations[event.id] = ToolInvocation(
                id=event.id,
                name=event.name,
                input=event.input,
            )
        elif isinstance(event, ToolResultEvent):
            inv = self.tool_invocations.get(event.tool_use_id)
            if inv is not None:
                inv.status = (
                    ToolInvocationStatus.ERROR
                    if event.is_error
                    else ToolInvocationStatus.OK
                )
        elif isinstance(event, DoneEvent):
            if event.usage:
                self.usage = TokenUsage.from_dict(event.usage)
            if event.cost_usd is not None:
                self.cost_usd = Decimal(str(event.cost_usd))
        elif isinstance(event, ErrorEvent):
            self.finish_reason = MessageFinishReason.ERROR

    def has_content(self) -> bool:
        return bool(self.text_parts)

    def build_message(self, conversation_id: UUID) -> Message:
        return Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content="".join(self.text_parts),
            finish_reason=self.finish_reason,
            tool_invocations=list(self.tool_invocations.values()),
            usage=self.usage,
            cost_usd=self.cost_usd,
        )


class SendMessageUseCase:
    def __init__(
        self,
        repository: ConversationRepository,
        runner: LLMRunner,
        assistant_writer: AssistantMessageWriter,
    ) -> None:
        self._repository = repository
        self._runner = runner
        self._assistant_writer = assistant_writer

    async def execute(
        self,
        conversation_id: UUID,
        user_text: str,
    ) -> AsyncIterator[ChatEvent]:
        conversation = await self._repository.get_by_id(conversation_id)
        if conversation is None or conversation.is_deleted:
            raise ConversationNotFoundError(conversation_id)

        history = await self._repository.list_messages(conversation_id)

        user_message = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=user_text,
        )
        await self._repository.add_message(user_message)

        prompt = _format_history_block(history) + user_text.strip()

        accumulator = _TurnAccumulator()
        try:
            async for event in self._runner.stream_turn(prompt):
                accumulator.consume(event)
                yield event
        except asyncio.CancelledError:
            accumulator.finish_reason = MessageFinishReason.INTERRUPTED
            raise
        except Exception:
            accumulator.finish_reason = MessageFinishReason.ERROR
            log.exception("send_message_stream_failed")
            raise
        finally:
            if accumulator.has_content():
                assistant_message = accumulator.build_message(conversation_id)
                _spawn(self._safe_write(assistant_message))

    async def _safe_write(self, message: Message) -> None:
        try:
            await self._assistant_writer.write(message)
        except Exception:
            log.exception(
                "persist_assistant_message_failed conversation_id=%s",
                message.conversation_id,
            )
