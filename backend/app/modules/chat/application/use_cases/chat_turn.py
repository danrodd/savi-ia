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
from collections.abc import AsyncIterator, Coroutine, Sequence
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
    ImageInput,
    SourcesEvent,
    SupersededEvent,
    TextDeltaEvent,
    TitleUpdateEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from app.modules.chat.domain.exceptions import (
    NoAssistantToRegenerateError,
    NothingToEditError,
    TooManyChatImagesError,
)
from app.modules.chat.domain.interfaces import (
    AssistantMessageWriter,
    ConversationTitleUpdater,
    LLMRunner,
)
from app.modules.company_knowledge.domain.services import TurnDocumentContext
from app.modules.conversations.domain.entities import ChatAttachment, Message, MessageRole
from app.modules.conversations.domain.exceptions import (
    ChatAttachmentUnavailableError,
    ConversationNotFoundError,
)
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.domain.value_objects import (
    ConversationOwner,
    MessageFinishReason,
    MessageSource,
    TokenUsage,
    ToolInvocation,
    ToolInvocationStatus,
)

log = logging.getLogger(__name__)

_HISTORY_TURNS = 20
_HISTORY_CHAR_LIMIT = 1500
_NEW_QUERY_MARKER = "=== Nueva consulta del usuario (responde esta) ==="
_TRUNCATION_MARKER = "Respuesta truncada por límite de tamaño"
# Texto que se le da al modelo (y al auto-título) cuando el mensaje es solo imágenes.
_IMAGE_ONLY_PROMPT = "(El usuario envió solo imagen(es), sin texto.)"
_IMAGE_ONLY_TITLE = "Imagen adjunta"

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
        if m.attachments:
            markers = "\n".join(f"[imagen adjunta: {a.filename}]" for a in m.attachments)
            body = f"{body}\n{markers}" if body else markers
        lines.append(f"{who}: {body}")
    lines.append(_NEW_QUERY_MARKER)
    return "\n\n".join(lines) + "\n\n"


def select_history_attachments(messages: list[Message], limit: int) -> list[ChatAttachment]:
    """Imágenes de mensajes anteriores que se reenvían al modelo.

    Solo mensajes del usuario activos (no reemplazados) dentro de la misma
    ventana del historial de texto, las más recientes primero, hasta `limit`.
    """
    selected: list[ChatAttachment] = []
    if limit <= 0:
        return selected
    for message in reversed(messages[-_HISTORY_TURNS:]):
        if message.role != MessageRole.USER or not message.is_active:
            continue
        for attachment in message.attachments:
            if len(selected) >= limit:
                return selected
            selected.append(attachment)
    return selected


def _title_text(user_text: str, attachments: Sequence[ChatAttachment]) -> str:
    """Texto para el auto-título: nunca vacío, aunque el mensaje sea solo imágenes."""
    if user_text.strip() or not attachments:
        return user_text
    return _IMAGE_ONLY_TITLE


class _TurnAccumulator:
    def __init__(self) -> None:
        self.text_parts: list[str] = []
        self.tool_invocations: dict[str, ToolInvocation] = {}
        self.usage: TokenUsage | None = None
        self.cost_usd: Decimal | None = None
        self.provider: str | None = None
        self.model: str | None = None
        self.finish_reason: MessageFinishReason = MessageFinishReason.COMPLETE
        self.sources: list[MessageSource] = []
        # Hubo una tool entre el último texto y el próximo.
        self._tool_since_text = False

    def separator_before(self, event: ChatEvent) -> TextDeltaEvent | None:
        """Salto de párrafo cuando el texto se reanuda después de una tool.

        Los modelos escriben un preámbulo ("Déjame revisar los datos..."),
        llaman a la tool y siguen escribiendo: sin separador el preámbulo
        quedaba pegado a la respuesta ("...los datos...En 2025 facturaste"),
        en pantalla y en el mensaje guardado.
        """
        if not (isinstance(event, TextDeltaEvent) and self._tool_since_text and event.text):
            return None
        if event.text[0].isspace() or self.text_parts[-1][-1:].isspace():
            return None
        return TextDeltaEvent(text="\n\n")

    def resolve_sources(self, document_context: TurnDocumentContext | None) -> list[MessageSource]:
        """Fuentes válidas citadas hasta ahora. Idempotente: se recalcula
        en `done` y otra vez al persistir tras una cancelación."""
        if document_context is None or not len(document_context.citations):
            return []
        self.sources = [
            MessageSource(
                ref=source.ref,
                refs=source.refs,
                document_id=source.document_id,
                version=source.version,
                title=source.title,
                pages=source.pages,
                url=source.url,
            )
            for source in document_context.citations.build_sources("".join(self.text_parts))
        ]
        return self.sources

    def consume(self, event: ChatEvent) -> None:
        if isinstance(event, TextDeltaEvent):
            self.text_parts.append(event.text)
            self._tool_since_text = False
            if (
                self.finish_reason == MessageFinishReason.COMPLETE
                and _TRUNCATION_MARKER in event.text
            ):
                self.finish_reason = MessageFinishReason.TRUNCATED
        elif isinstance(event, ToolUseEvent):
            self._tool_since_text = bool(self.text_parts)
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
            self.provider = event.provider
            self.model = event.model
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
            provider=self.provider,
            model=self.model,
            sources=list(self.sources),
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
        attachment_ids: Sequence[UUID] = (),
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
            conversation.user_id, conversation.owner_erp_database_id
        ):
            raise ConversationNotFoundError(conversation_id)

        if action == ChatAction.EDIT_LAST:
            active = await self._repository.list_messages(conversation_id)
            if not active:
                raise NothingToEditError
            last = active[-1]
            if last.role == MessageRole.USER:
                replaced_user = last
            elif (
                last.role == MessageRole.ASSISTANT
                and len(active) >= 2
                and (active[-2].role == MessageRole.USER)
            ):
                replaced_user = active[-2]
            else:
                raise NothingToEditError
            await self._validate_attachments(attachment_ids, expected_owner, replaced_user)
            return conversation.erp_database_id
        elif action == ChatAction.REGENERATE:
            active = await self._repository.list_messages(conversation_id)
            if (
                not active
                or active[-1].role != MessageRole.ASSISTANT
                or len(active) < 2
                or active[-2].role != MessageRole.USER
            ):
                raise NoAssistantToRegenerateError
            # Reusa las imágenes del último mensaje: `attachment_ids` no aplica.
        else:
            await self._validate_attachments(attachment_ids, expected_owner, None)

        return conversation.erp_database_id

    async def _validate_attachments(
        self,
        attachment_ids: Sequence[UUID],
        owner: ConversationOwner | None,
        replaced_user: Message | None,
    ) -> None:
        """Cada imagen existe, es del usuario y está libre (o, al editar,
        pertenece al mensaje que se reemplaza)."""
        if not attachment_ids:
            return
        limit = self._settings.chat_images_per_message
        if len(attachment_ids) > limit:
            raise TooManyChatImagesError(limit)
        found = {a.id: a for a in await self._repository.get_attachments(attachment_ids)}
        for attachment_id in attachment_ids:
            attachment = found.get(attachment_id)
            # Inexistente y ajena dan el mismo mensaje: no confirma ids de otros.
            if attachment is None or (
                owner is not None
                and not owner.owns(attachment.user_id, attachment.owner_erp_database_id)
            ):
                raise ChatAttachmentUnavailableError(
                    "Alguna de las imágenes adjuntas no existe o no está disponible."
                )
            if attachment.message_id is not None and (
                replaced_user is None or attachment.message_id != replaced_user.id
            ):
                raise ChatAttachmentUnavailableError(
                    "Alguna de las imágenes adjuntas ya se usó en otro mensaje."
                )

    async def execute(
        self,
        conversation_id: UUID,
        action: ChatAction,
        message: str | None,
        *,
        allowed_modules: frozenset[ModuleCode] | None = None,
        erp_database_id: UUID | None = None,
        document_context: TurnDocumentContext | None = None,
        attachment_ids: Sequence[UUID] = (),
    ) -> AsyncIterator[ChatEvent]:
        # `validate` ya corrió desde el endpoint; aún así re-leemos la
        # conversación para conocer `title_locked` y el título.
        conversation = await self._repository.get_by_id(conversation_id)
        if conversation is None or conversation.is_deleted:
            raise ConversationNotFoundError(conversation_id)

        is_renamable = not conversation.title_locked and conversation.has_default_title

        # Con solo imágenes el mensaje llega vacío (lo valida `ChatRequest`).
        text = message or ""

        if action == ChatAction.SEND:
            async for event in self._execute_send(
                conversation_id,
                text,
                attachment_ids=attachment_ids,
                is_renamable=is_renamable,
                allowed_modules=allowed_modules,
                erp_database_id=erp_database_id,
                document_context=document_context,
            ):
                yield event
        elif action == ChatAction.EDIT_LAST:
            async for event in self._execute_edit_last(
                conversation_id,
                text,
                attachment_ids=attachment_ids,
                is_renamable=is_renamable,
                allowed_modules=allowed_modules,
                erp_database_id=erp_database_id,
                document_context=document_context,
            ):
                yield event
        elif action == ChatAction.REGENERATE:
            async for event in self._execute_regenerate(
                conversation_id,
                allowed_modules=allowed_modules,
                erp_database_id=erp_database_id,
                document_context=document_context,
            ):
                yield event

    # ── send ──────────────────────────────────────────────────────────────
    async def _execute_send(
        self,
        conversation_id: UUID,
        user_text: str,
        *,
        attachment_ids: Sequence[UUID] = (),
        is_renamable: bool,
        allowed_modules: frozenset[ModuleCode] | None,
        erp_database_id: UUID | None = None,
        document_context: TurnDocumentContext | None = None,
    ) -> AsyncIterator[ChatEvent]:
        # Solo los últimos: `_format_history_block` descarta el resto igual.
        # Traer la conversación entera para tirar casi todo era trabajo puro
        # en cada turno de una conversación larga.
        history = await self._repository.list_messages(conversation_id, limit=_HISTORY_TURNS)
        user_message = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=user_text,
        )
        if attachment_ids:
            # Mensaje e imágenes en la misma transacción.
            user_message = await self._repository.add_user_message_with_attachments(
                user_message, link_attachment_ids=attachment_ids
            )
        else:
            await self._repository.add_message(user_message)
        prompt, images = await self._build_turn_input(history, user_text, user_message.attachments)

        async for event in self._stream_assistant_turn(
            conversation_id=conversation_id,
            prompt=prompt,
            images=images,
            supersedes_id=None,
            user_text_for_title=(
                _title_text(user_text, user_message.attachments) if is_renamable else None
            ),
            allowed_modules=allowed_modules,
            erp_database_id=erp_database_id,
            document_context=document_context,
        ):
            yield event

    # ── edit_last ─────────────────────────────────────────────────────────
    async def _execute_edit_last(
        self,
        conversation_id: UUID,
        new_user_text: str,
        *,
        attachment_ids: Sequence[UUID] = (),
        is_renamable: bool,
        allowed_modules: frozenset[ModuleCode] | None,
        erp_database_id: UUID | None = None,
        document_context: TurnDocumentContext | None = None,
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
        if attachment_ids:
            # Las imágenes del mensaje que se reemplaza se COPIAN: la versión
            # anterior conserva las suyas. Las recién subidas se enlazan.
            replaced_ids = {a.id for a in old_user.attachments}
            new_user = await self._repository.add_user_message_with_attachments(
                new_user,
                link_attachment_ids=[i for i in attachment_ids if i not in replaced_ids],
                copy_attachment_ids=[i for i in attachment_ids if i in replaced_ids],
            )
        else:
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
        prompt, images = await self._build_turn_input(
            history_pre, new_user_text, new_user.attachments
        )

        async for event in self._stream_assistant_turn(
            conversation_id=conversation_id,
            prompt=prompt,
            images=images,
            supersedes_id=old_assistant.id if old_assistant else None,
            user_text_for_title=(
                _title_text(new_user_text, new_user.attachments) if is_renamable else None
            ),
            allowed_modules=allowed_modules,
            erp_database_id=erp_database_id,
            document_context=document_context,
        ):
            yield event

    # ── regenerate ────────────────────────────────────────────────────────
    async def _execute_regenerate(
        self,
        conversation_id: UUID,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
        erp_database_id: UUID | None = None,
        document_context: TurnDocumentContext | None = None,
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
        prompt, images = await self._build_turn_input(
            history_pre, last_user.content, last_user.attachments
        )

        async for event in self._stream_assistant_turn(
            conversation_id=conversation_id,
            prompt=prompt,
            images=images,
            supersedes_id=old_assistant.id,
            user_text_for_title=None,  # regenerate nunca regenera el título
            allowed_modules=allowed_modules,
            erp_database_id=erp_database_id,
            document_context=document_context,
        ):
            yield event

    # ── helpers comunes ───────────────────────────────────────────────────
    async def _build_turn_input(
        self,
        history_pre: list[Message],
        user_text: str,
        current_attachments: Sequence[ChatAttachment],
    ) -> tuple[str, list[ImageInput]]:
        """Prompt de texto + imágenes que viajan al modelo.

        Imágenes: todas las del turno actual y, además, hasta
        `chat_history_images_max` de mensajes anteriores (las más recientes
        primero). Los bytes se leen solo de las que realmente se envían.
        """
        text = user_text.strip()
        if not text and current_attachments:
            text = _IMAGE_ONLY_PROMPT
        prompt = _format_history_block(history_pre) + text

        previous = select_history_attachments(history_pre, self._settings.chat_history_images_max)
        wanted = [*previous, *current_attachments]
        if not wanted:
            return prompt, []
        contents = await self._repository.get_attachment_contents([a.id for a in wanted])
        current_ids = {a.id for a in current_attachments}
        images: list[ImageInput] = []
        for attachment in wanted:
            data = contents.get(attachment.id)
            if data is None:
                log.warning("chat_attachment_bytes_missing attachment_id=%s", attachment.id)
                continue
            images.append(
                ImageInput(
                    mime=attachment.mime,
                    data=data,
                    filename=attachment.filename,
                    from_current_turn=attachment.id in current_ids,
                )
            )
        return prompt, images

    async def _stream_assistant_turn(
        self,
        *,
        conversation_id: UUID,
        prompt: str,
        images: Sequence[ImageInput] = (),
        supersedes_id: UUID | None,
        user_text_for_title: str | None,
        allowed_modules: frozenset[ModuleCode] | None,
        erp_database_id: UUID | None = None,
        document_context: TurnDocumentContext | None = None,
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
                document_context=document_context,
                images=images,
            ):
                separator = accumulator.separator_before(event)
                if separator is not None:
                    accumulator.consume(separator)
                    yield separator
                accumulator.consume(event)
                if isinstance(event, DoneEvent):
                    # Las fuentes llegan ANTES de `done`: el frontend cierra
                    # el mensaje al recibir `done`.
                    sources = accumulator.resolve_sources(document_context)
                    if sources:
                        yield SourcesEvent(sources=[src.to_dict() for src in sources])
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
                # Con cancelación no hubo `done`: se resuelven acá las
                # referencias válidas citadas hasta el corte.
                accumulator.resolve_sources(document_context)
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
