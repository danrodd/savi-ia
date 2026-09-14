from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.value_objects import ModelInfo


@dataclass(frozen=True, slots=True)
class ProbeResult:
    ok: bool
    detail: str
    models: tuple[ModelInfo, ...] = ()


class ProviderProbe(ABC):
    """Prueba una credencial contra el proveedor real.

    **Nunca levanta**: una key inválida es `ok=False` con un detalle
    accionable, igual que `ConnectionTester` para las bases del ERP. Es
    entrada mal cargada, no un error del servidor.
    """

    @abstractmethod
    async def test(self, config: LlmProviderConfig) -> ProbeResult: ...

    @abstractmethod
    async def list_models(self, config: LlmProviderConfig) -> list[ModelInfo]: ...
