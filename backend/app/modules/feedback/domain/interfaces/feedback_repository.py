from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.modules.feedback.domain.entities import MessageFeedback
from app.modules.feedback.domain.value_objects import (
    FeedbackFilters,
    FeedbackPage,
    FeedbackReportItem,
    FeedbackSummary,
)


@dataclass(frozen=True, slots=True)
class FeedbackTarget:
    """Lo mínimo de un mensaje (y su conversación) para decidir si se califica."""

    message_id: UUID
    conversation_id: UUID
    role: str
    is_superseded: bool
    conversation_deleted: bool
    conversation_user_id: int | None
    conversation_owner_database_id: UUID | None


class FeedbackRepository(ABC):
    """Persistencia de las calificaciones del propio usuario."""

    @abstractmethod
    async def get_target(self, conversation_id: UUID, message_id: UUID) -> FeedbackTarget | None:
        """El mensaje, solo si pertenece a esa conversación."""

    @abstractmethod
    async def upsert(self, feedback: MessageFeedback) -> MessageFeedback:
        """Crea la calificación o reemplaza la que el usuario ya tenía."""

    @abstractmethod
    async def delete(self, message_id: UUID, *, user_id: int, owner_erp_database_id: UUID) -> None:
        """Quita la calificación del usuario. Idempotente."""

    @abstractmethod
    async def list_for_messages(
        self,
        message_ids: Sequence[UUID],
        *,
        user_id: int,
        owner_erp_database_id: UUID,
    ) -> dict[UUID, MessageFeedback]:
        """Calificaciones del usuario sobre esos mensajes, por `message_id`."""


class FeedbackReportRepository(ABC):
    """Lectura administrativa. Todo acotado a la base del administrador."""

    @abstractmethod
    async def list_feedback(
        self,
        *,
        owner_erp_database_id: UUID,
        filters: FeedbackFilters,
        limit: int,
        offset: int,
    ) -> FeedbackPage: ...

    @abstractmethod
    async def export_rows(
        self,
        *,
        owner_erp_database_id: UUID,
        filters: FeedbackFilters,
        max_rows: int,
    ) -> list[FeedbackReportItem]: ...

    @abstractmethod
    async def summary(
        self,
        *,
        owner_erp_database_id: UUID,
        filters: FeedbackFilters,
    ) -> FeedbackSummary: ...
