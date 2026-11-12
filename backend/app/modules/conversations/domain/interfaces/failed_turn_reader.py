"""Puerto de lectura de los turnos que terminaron en error.

Para la vista de Administración: el administrador del cliente ve qué falló, con
el código de soporte, sin que haya que pedirle el log del equipo.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class FailedTurn:
    message_id: UUID
    conversation_id: UUID
    conversation_title: str | None
    user_id: int | None
    created_at: datetime
    error_code: str | None
    error_message: str | None
    support_code: str | None
    provider: str | None
    model: str | None
    erp_queries: int


class FailedTurnReader(ABC):
    @abstractmethod
    async def recent(self, owner_erp_database_id: UUID, limit: int) -> list[FailedTurn]:
        """Los más recientes primero, de las conversaciones de esa base."""
