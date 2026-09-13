"""Use case del turno de chat — orquesta send / edit_last / regenerate.

Diseño:
- Cada acción tiene su propio camino de preparación (qué supersede, qué
  insertar, cómo armar el prompt), pero todas convergen en
  `_stream_assistant_turn` que ejecuta el LLM, acumula la respuesta y
  despacha la persistencia con un writer de sesión independiente
  (sobrevive a la cancelación del cliente).
- Auto-título: dispara fase 1 + fase 2 solo en `send` y `edit_last`, no
  en `regenerate` (donde el contenido del user no cambia).
- Cuando hay un assistant viejo siendo "reemplazado" (edit_last con
  asst posterior, o regenerate), pasamos su id al writer como
  `supersedes_id` para que enlace el nuevo al viejo (`superseded_by_id`)
  en la misma transacción.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Coroutine
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.infrastructure.config import Settings
from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.chat.application.requests import ChatAction
from app.modules.chat.domain.entities import (
    ChatEvent,
    DoneEvent,
    ErrorEvent,
    SupersededEvent,
    TextDeltaEvent,
    TitleUpdateEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from app.modules.chat.domain.exceptions import (
    NoAssistantToRegenerateError,
    NothingToEditError,
)
from app.modules.chat.domain.interfaces import (
    AssistantMessageWriter,
    ConversationTitleUpdater,
    LLMRunner,
)
from app.modules.conversations.domain.entities import Message, MessageRole
from app.modules.conversations.domain.exceptions import ConversationNotFoundError
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.domain.value_objects import (
    ConversationOwner,
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

_BG_TASKS: set[asyncio.Task[Any]] = set()


def _spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
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
        if m.role == MessageRole.ASSISTANT and m.finish_reason == MessageFinishReason.INTERRUPTED:
            body += "\n\n[respuesta interrumpida por el usuario]"
        lines.append(f"{who}: {body}")
    lines.append(_NEW_QUERY_MARKER)
    return "\n\n".join(lines) + "\n\n"


class _TurnAccumulator:
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
                    ToolInvocationStatus.ERROR if event.is_error else ToolInvocationStatus.OK
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


class ChatTurnUseCase:
    def __init__(
        self,
        repository: ConversationRepository,
        runner: LLMRunner,
        assistant_writer: AssistantMessageWriter,
        title_updater: ConversationTitleUpdater,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._runner = runner
        self._assistant_writer = assistant_writer
        self._title_updater = title_updater
        self._settings = settings

    async def validate(
        self,
        conversation_id: UUID,
        action: ChatAction,
        *,
        expected_owner: ConversationOwner | None = None,
    ) -> UUID | None:
        """Chequea precondiciones antes de devolver el StreamingResponse.

        Si algo falla, levanta una excepción de dominio que el handler
        global convierte a 4xx — esto se hace fuera del SSE para que
        FastAPI pueda emitir el status code correcto (dentro del stream
        los headers HTTP ya están enviados con 200).

        Devuelve el `erp_database_id` de la conversación: el endpoint lo
        necesita para chequear que la base siga disponible y para resolver
        los módulos contra ella, ambas cosas antes de abrir el SSE."""
        conversation = await self._repository.get_by_id(conversation_id)
        if conversation is None or conversation.is_deleted:
            raise ConversationNotFoundError(conversation_id)
        # Ownership: si el endpoint pasa el dueño esperado y no coincide,
        # tratamos como "no existe" (no leak de existencia).
        if expected_owner is not None and not expected_owner.owns(
            conversation.user_id, conversation.erp_database_id
        ):
            raise ConversationNotFoundError(conversation_id)

        if action == ChatAction.EDIT_LAST:
            active = await self._repository.list_messages(conversation_id)
            if not active:
                raise NothingToEditError
            last = active[-1]
            if last.role == MessageRole.USER:
                return conversation.erp_database_id
            if (
                last.role == MessageRole.ASSISTANT
                and len(active) >= 2
                and (active[-2].role == MessageRole.USER)
            ):
                return conversation.erp_database_id
            raise NothingToEditError
        elif action == ChatAction.REGENERATE:
            active = await self._repository.list_messages(conversation_id)
            if (
                not active
                or active[-1].role != MessageRole.ASSISTANT
                or len(active) < 2
                or active[-2].role != MessageRole.USER
            ):
                raise NoAssistantToRegenerateError

        return conversation.erp_database_id

    async def execute(
        self,
        conversation_id: UUID,
        action: ChatAction,
        message: str | None,
        *,
        allowed_modules: frozenset[ModuleCode] | None = None,
        erp_database_id: UUID | None = None,
    ) -> AsyncIterator[ChatEvent]:
        # `validate` ya corrió desde el endpoint; aún así re-leemos la
        # conversación para conocer `title_locked` y el título.
        conversation = await self._repository.get_by_id(conversation_id)
        if conversation is None or conversation.is_deleted:
            raise ConversationNotFoundError(conversation_id)

        is_renamable = not conversation.title_locked and conversation.has_default_title

        if action == ChatAction.SEND:
            assert message is not None  # noqa: S101 — validated by ChatRequest
            async for event in self._execute_send(
                conversation_id,
                message,
                is_renamable=is_renamable,
                allowed_modules=allowed_modules,
                erp_database_id=erp_database_id,
            ):
                yield event
        elif action == ChatAction.EDIT_LAST:
            assert message is not None  # noqa: S101
            async for event in self._execute_edit_last(
                conversation_id,
                message,
                is_renamable=is_renamable,
                allowed_modules=allowed_modules,
                erp_database_id=erp_database_id,
            ):
                yield event
        elif action == ChatAction.REGENERATE:
            async for event in self._execute_regenerate(
                conversation_id,
                allowed_modules=allowed_modules,
                erp_database_id=erp_database_id,
            ):
                yield event

    # ── send ──────────────────────────────────────────────────────────────
    async def _execute_send(
        self,
        conversation_id: UUID,
        user_text: str,
        *,
        is_renamable: bool,
        allowed_modules: frozenset[ModuleCode] | None,
        erp_database_id: UUID | None = None,
    ) -> AsyncIterator[ChatEvent]:
        history = await self._repository.list_messages(conversation_id)
        user_message = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=user_text,
        )
        await self._repository.add_message(user_message)
        prompt = _format_history_block(history) + user_text.strip()

        async for event in self._stream_assistant_turn(
            conversation_id=conversation_id,
            prompt=prompt,
            supersedes_id=None,
            user_text_for_title=user_text if is_renamable else None,
            allowed_modules=allowed_modules,
            erp_database_id=erp_database_id,
        ):
            yield event

    # ── edit_last ─────────────────────────────────────────────────────────
    async def _execute_edit_last(
        self,
        conversation_id: UUID,
        new_user_text: str,
        *,
        is_renamable: bool,
        allowed_modules: frozenset[ModuleCode] | None,
        erp_database_id: UUID | None = None,
    ) -> AsyncIterator[ChatEvent]:
        active = await self._repository.list_messages(conversation_id)
        if not active:
            raise NothingToEditError

        last = active[-1]
        # Identificar qué supersede: siempre el último user activo;
        # si después de él hay un assistant activo, también ese.
        if last.role == MessageRole.USER:
            old_user = last
            old_assistant: Message | None = None
        elif last.role == MessageRole.ASSISTANT:
            if len(active) < 2 or active[-2].role != MessageRole.USER:
                raise NothingToEditError
            old_user = active[-2]
            old_assistant = last
        else:
            raise NothingToEditError

        # 1) Insertar el nuevo user.
        new_user = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=new_user_text,
        )
        await self._repository.add_message(new_user)

        # 2) Marcar el user viejo como superseded apuntando al nuevo.
        await self._repository.supersede_messages([old_user.id], superseded_by_id=new_user.id)

        # 3) Si había assistant, también supersede (el link a su versión
        #    nueva lo cierra el writer cuando termine el stream).
        superseded_ids = [str(old_user.id)]
        if old_assistant is not None:
            await self._repository.supersede_messages([old_assistant.id])
            superseded_ids.append(str(old_assistant.id))

        # 4) Notificar al frontend qué desaparece del hilo activo.
        yield SupersededEvent(message_ids=superseded_ids)

        # 5) Reconstruir historial activo y armar el prompt.
        new_active = await self._repository.list_messages(conversation_id)
        history_pre = new_active[:-1]  # sin el nuevo user
        prompt = _format_history_block(history_pre) + new_user_text.strip()

        async for event in self._stream_assistant_turn(
            conversation_id=conversation_id,
            prompt=prompt,
            supersedes_id=old_assistant.id if old_assistant else None,
            user_text_for_title=new_user_text if is_renamable else None,
            allowed_modules=allowed_modules,
            erp_database_id=erp_database_id,
        ):
            yield event

    # ── regenerate ────────────────────────────────────────────────────────
    async def _execute_regenerate(
        self,
        conversation_id: UUID,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
        erp_database_id: UUID | None = None,
    ) -> AsyncIterator[ChatEvent]:
        active = await self._repository.list_messages(conversation_id)
        if not active or active[-1].role != MessageRole.ASSISTANT:
            raise NoAssistantToRegenerateError

        old_assistant = active[-1]
        if len(active) < 2 or active[-2].role != MessageRole.USER:
            # Defensa: una conversación bien formada siempre tiene un
            # user inmediatamente antes del assistant.
            raise NoAssistantToRegenerateError
        last_user = active[-2]

        await self._repository.supersede_messages([old_assistant.id])
        yield SupersededEvent(message_ids=[str(old_assistant.id)])

        # Prompt reusa el último user (no se inserta uno nuevo).
        history_pre = active[:-2]  # todo lo de antes del par user/asst
        prompt = _format_history_block(history_pre) + last_user.content.strip()

        async for event in self._stream_assistant_turn(
            conversation_id=conversation_id,
            prompt=prompt,
            supersedes_id=old_assistant.id,
            user_text_for_title=None,  # regenerate nunca regenera el título
            allowed_modules=allowed_modules,
            erp_database_id=erp_database_id,
        ):
            yield event

    # ── helper común ──────────────────────────────────────────────────────
    async def _stream_assistant_turn(
        self,
        *,
        conversation_id: UUID,
        prompt: str,
        supersedes_id: UUID | None,
        user_text_for_title: str | None,
        allowed_modules: frozenset[ModuleCode] | None,
        erp_database_id: UUID | None = None,
    ) -> AsyncIterator[ChatEvent]:
        title_phase1_task: asyncio.Task[Any] | None = None
        title_phase1_emitted = False
        if user_text_for_title is not None:
            title_phase1_task = _spawn(
                self._title_updater.update_from_user(conversation_id, user_text_for_title)
            )

        accumulator = _TurnAccumulator()
        try:
            async for event in self._runner.stream_turn(
                prompt,
                conversation_id=conversation_id,
                allowed_modules=allowed_modules,
                erp_database_id=erp_database_id,
            ):
                accumulator.consume(event)
                yield event
                if (
                    title_phase1_task is not None
                    and not title_phase1_emitted
                    and title_phase1_task.done()
                ):
                    title = self._read_title_task(title_phase1_task)
                    title_phase1_emitted = True
                    if title:
                        yield TitleUpdateEvent(title=title)
        except asyncio.CancelledError:
            accumulator.finish_reason = MessageFinishReason.INTERRUPTED
            raise
        except Exception:
            accumulator.finish_reason = MessageFinishReason.ERROR
            log.exception("chat_turn_stream_failed")
            raise
        finally:
            if accumulator.has_content():
                assistant_message = accumulator.build_message(conversation_id)
                _spawn(self._safe_write(assistant_message, supersedes_id=supersedes_id))

        if (
            user_text_for_title is not None
            and accumulator.finish_reason == MessageFinishReason.COMPLETE
            and accumulator.has_content()
        ):
            if title_phase1_task is not None and not title_phase1_emitted:
                drained = await self._await_title(title_phase1_task, max_wait_s=3.0)
                title_phase1_emitted = True
                if drained:
                    yield TitleUpdateEvent(title=drained)

            phase2_task = _spawn(
                self._title_updater.update_from_turn(
                    conversation_id,
                    user_text_for_title,
                    "".join(accumulator.text_parts),
                )
            )
            refined = await self._await_title(
                phase2_task,
                max_wait_s=self._settings.title_phase2_timeout_s,
            )
            if refined:
                yield TitleUpdateEvent(title=refined)

    async def _safe_write(self, message: Message, *, supersedes_id: UUID | None) -> None:
        try:
            await self._assistant_writer.write(message, supersedes_id=supersedes_id)
        except Exception:
            log.exception(
                "persist_assistant_message_failed conversation_id=%s",
                message.conversation_id,
            )

    @staticmethod
    def _read_title_task(task: asyncio.Task[Any]) -> str | None:
        try:
            result = task.result()
        except Exception:
            log.exception("title_task_failed")
            return None
        return result if isinstance(result, str) and result else None

    @staticmethod
    async def _await_title(task: asyncio.Task[Any], *, max_wait_s: float) -> str | None:
        try:
            async with asyncio.timeout(max_wait_s):
                result = await asyncio.shield(task)
        except TimeoutError:
            return None
        except Exception:
            log.exception("title_await_failed")
            return None
        return result if isinstance(result, str) and result else None


__all__ = ["ChatTurnUseCase"]
