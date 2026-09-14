"""Puerto para saber con qué proveedor de IA atender el turno.

El chat no importa `llm_providers`: depende de este puerto, y la
implementación vive allá. Se resuelve **por turno**, así cambiar el
proveedor o su credencial desde administración aplica sin reiniciar.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """USD por millón de tokens."""

    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0


@dataclass(frozen=True, slots=True)
class ActiveProvider:
    kind: str
    chat_model: str
    title_model: str
    credential_kind: str
    # En claro, solo en memoria del proceso. Nunca va a un log.
    credential: str | None = field(default=None, repr=False)
    pricing: dict[str, ModelPrice] = field(default_factory=dict[str, ModelPrice])


class ActiveProviderResolver(ABC):
    @abstractmethod
    async def resolve(self) -> ActiveProvider:
        """Levanta `LlmProviderUnavailableError` si no hay uno usable."""
