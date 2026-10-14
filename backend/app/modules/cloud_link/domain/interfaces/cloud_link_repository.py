from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime

from app.modules.cloud_link.domain.entities import CloudLinkState, StreamWatermark


class CloudLinkRepository(ABC):
    @abstractmethod
    async def get(self) -> CloudLinkState:
        """El estado. La primera vez crea la fila y genera `pseudonym_key` e
        `install_id`, antes de que exista cualquier vinculación."""

    @abstractmethod
    async def update(self, mutate: Callable[[CloudLinkState], None]) -> CloudLinkState:
        """Lee, aplica `mutate` y guarda en una sola transacción, así dos
        tareas que escriben campos distintos no se pisan."""

    @abstractmethod
    async def get_watermark(self, stream: str) -> StreamWatermark | None: ...

    @abstractmethod
    async def list_watermarks(self) -> list[StreamWatermark]: ...

    @abstractmethod
    async def save_watermark(self, watermark: StreamWatermark) -> None: ...

    @abstractmethod
    async def reset_watermarks(self, streams: list[str], at: datetime) -> None:
        """Borra todas las marcas y deja `streams` en `at` (id vacío)."""

    @abstractmethod
    async def delete_watermarks(self) -> None: ...
