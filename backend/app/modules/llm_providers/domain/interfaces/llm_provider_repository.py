from __future__ import annotations

from abc import ABC, abstractmethod

from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.value_objects import ProviderKind


class LlmProviderRepository(ABC):
    @abstractmethod
    async def get(self, provider: ProviderKind) -> LlmProviderConfig | None: ...

    @abstractmethod
    async def get_active(self) -> LlmProviderConfig | None: ...

    @abstractmethod
    async def list_all(self) -> list[LlmProviderConfig]: ...

    @abstractmethod
    async def count(self) -> int: ...

    @abstractmethod
    async def save(self, config: LlmProviderConfig) -> None:
        """Crea o actualiza la fila del proveedor. No toca `is_active`
        de una fila existente: eso es de `activate`."""

    @abstractmethod
    async def activate(self, provider: ProviderKind) -> None:
        """Baja el activo anterior y sube este en la misma transacción."""
