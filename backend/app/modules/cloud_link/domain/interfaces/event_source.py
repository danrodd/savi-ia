from abc import ABC, abstractmethod
from datetime import datetime

from app.modules.cloud_link.domain.entities import Cursor, SyncEvent
from app.modules.cloud_link.domain.value_objects import SyncStream


class EventSource(ABC):
    """Extractor incremental de un stream. Lee las tablas existentes y mapea
    cada fila a la lista blanca del contrato: aquí es donde se garantiza que
    nunca viaja contenido."""

    stream: SyncStream

    @abstractmethod
    async def read_batch(self, after: Cursor, limit: int) -> list[SyncEvent]:
        """Hasta `limit` eventos con `(created_at, id) > after`, en orden."""


class SnapshotSource(ABC):
    """Extractor de un stream que no es incremental (inventario de bases)."""

    stream: SyncStream

    @abstractmethod
    async def snapshot(self, now: datetime) -> list[SyncEvent]: ...
