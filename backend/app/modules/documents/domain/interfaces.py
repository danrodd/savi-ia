from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.modules.documents.domain.result_set import ResultSet


class ResultSetRepository(ABC):
    @abstractmethod
    async def add(self, result_set: ResultSet) -> None: ...

    @abstractmethod
    async def get_owned(
        self, result_set_id: UUID, *, user_id: int, owner_erp_database_id: UUID
    ) -> ResultSet | None:
        """El conjunto si pertenece a una conversación de ese dueño y no venció."""

    @abstractmethod
    async def created_since(self, conversation_id: UUID, since: datetime) -> list[ResultSet]:
        """Los de la conversación creados desde `since` (los de un turno), en orden."""
