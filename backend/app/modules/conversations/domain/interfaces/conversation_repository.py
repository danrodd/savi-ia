from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.modules.conversations.domain.entities import ChatAttachment, Conversation, Message


class ConversationRepository(ABC):
    @abstractmethod
    async def save(self, conversation: Conversation) -> Conversation: ...

    @abstractmethod
    async def get_by_id(self, conversation_id: UUID) -> Conversation | None: ...

    @abstractmethod
    async def list_for_user(
        self,
        user_id: int | None,
        *,
        owner_erp_database_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]: ...

    @abstractmethod
    async def update_title(
        self,
        conversation_id: UUID,
        new_title: str,
        *,
        respect_lock: bool = True,
        lock: bool = False,
    ) -> str | None:
        """Cambia el título de una conversación.

        - `respect_lock`: si True y la conversación tiene `title_locked`,
          NO se hace nada y devuelve None. Lo usan los autotítulos.
        - `lock`: si True, marca `title_locked=true` tras actualizar.
          Lo usa el endpoint manual de renombre.

        Devuelve el título efectivamente aplicado, o None si no se aplicó
        (por lock o por conversación inexistente).
        """

    @abstractmethod
    async def soft_delete(self, conversation_id: UUID) -> bool:
        """Marca la conversación como eliminada (`deleted_at=now()`).

        Idempotente: si la conversación ya estaba eliminada, respeta el
        `deleted_at` original (vía `COALESCE`). Si no existe, devuelve
        `False`. Si existe (esté ya eliminada o no), devuelve `True`.

        No bloquea ni cancela los turnos en curso: los writers
        independientes (`AssistantMessageWriter`,
        `ConversationTitleUpdater`) siguen insertando contra la FK por
        `conversations.id`. Esos escritos quedan asociados a una
        conversación invisible al usuario, lo cual es el comportamiento
        esperado del soft delete.
        """

    @abstractmethod
    async def add_message(self, message: Message) -> Message: ...

    @abstractmethod
    async def add_user_message_with_attachments(
        self,
        message: Message,
        *,
        link_attachment_ids: Sequence[UUID] = (),
        copy_attachment_ids: Sequence[UUID] = (),
    ) -> Message:
        """Inserta el mensaje del usuario y le asocia sus imágenes en una
        sola transacción.

        - `link_attachment_ids`: adjuntos sin mensaje (recién subidos); se
          enlazan tal cual. Si alguno ya no está libre, levanta
          `ChatAttachmentUnavailableError` y no queda nada escrito.
        - `copy_attachment_ids`: adjuntos de OTRO mensaje (el que se está
          reemplazando al editar); se duplican (fila + bytes) para que la
          versión anterior conserve los suyos.

        Devuelve el mensaje con `attachments` ya cargados (en ese orden)."""

    @abstractmethod
    async def get_attachments(self, attachment_ids: Sequence[UUID]) -> list[ChatAttachment]:
        """Metadata de los adjuntos que existan (los ausentes se omiten)."""

    @abstractmethod
    async def get_attachment_contents(self, attachment_ids: Sequence[UUID]) -> dict[UUID, bytes]:
        """Bytes de esos adjuntos. Solo para las imágenes que realmente se
        envían al modelo: listar mensajes nunca los carga."""

    @abstractmethod
    async def list_messages(
        self,
        conversation_id: UUID,
        *,
        include_superseded: bool = False,
        limit: int | None = None,
    ) -> list[Message]:
        """Lista los mensajes de la conversación.

        Por default sólo devuelve el hilo activo
        (`superseded_at IS NULL`), ordenado por `created_at` ascendente.

        Con `include_superseded=True` devuelve también las versiones
        anteriores — útil para reconstruir trazabilidad en la UI.

        `limit` devuelve los N **más recientes** (igual en orden ascendente).
        Lo usa el armado del historial del turno, que solo mira los últimos
        mensajes: sin esto traía la conversación entera para descartar casi
        todo, y una conversación larga pagaba ese costo en cada turno.
        """

    @abstractmethod
    async def get_last_active_message(
        self,
        conversation_id: UUID,
    ) -> Message | None:
        """Devuelve el último mensaje activo (más reciente por created_at)
        o None si la conversación no tiene mensajes activos."""

    @abstractmethod
    async def supersede_messages(
        self,
        message_ids: list[UUID],
        *,
        superseded_by_id: UUID | None = None,
    ) -> None:
        """Marca un conjunto de mensajes como superseded en una sola
        operación. Setea `superseded_at=now()`. Si `superseded_by_id`
        está dado, lo aplica a todos (uso normal: el USER viejo apunta al
        USER nuevo; el ASSISTANT viejo queda con None hasta que el nuevo
        ASSISTANT se persiste y el writer lo enlaza)."""
