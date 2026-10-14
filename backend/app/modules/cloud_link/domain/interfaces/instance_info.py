from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class InstanceInfo:
    name: str
    deployment_mode: str
    version: str | None
    commit: str | None
    os: str
    agent_db_engine: str
    fingerprint: str
    started_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LlmTelemetry:
    provider: str | None = None
    model: str | None = None
    credential_kind: str | None = None
    usable: bool | None = None


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    llm: LlmTelemetry = field(default_factory=LlmTelemetry)
    databases_total: int = 0
    databases_usable: int = 0
    databases_unreadable: int = 0
    active_sessions: int = 0
    # Códigos cortos, sin detalle.
    warnings: list[str] = field(default_factory=list[str])
    tls: bool | None = None


class InstanceInfoProvider(ABC):
    @abstractmethod
    def describe(self, install_id: UUID) -> InstanceInfo: ...


class LocalTelemetry(ABC):
    """Lo que el heartbeat cuenta del estado local (sin contenido)."""

    @abstractmethod
    async def collect(self) -> TelemetrySnapshot: ...
