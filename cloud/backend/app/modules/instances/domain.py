from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from app.shared.errors import DomainError

FINGERPRINT_MISMATCH = "fingerprint_mismatch"
MANUAL_REASON = "manual"


class InstanceStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


@dataclass(frozen=True)
class Instance:
    id: UUID
    client_id: UUID
    name: str
    deployment_mode: str
    os: str
    agent_db_engine: str
    version: str | None
    commit: str | None
    status: InstanceStatus
    status_reason: str | None
    secret_hash: bytes
    fingerprint: str
    enrolled_at: datetime
    created_at: datetime
    updated_at: datetime
    previous_secret_hash: bytes | None = None
    previous_secret_expires_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_heartbeat: dict[str, Any] | None = None
    clock_skew_seconds: int | None = None


class InstanceNotFound(DomainError):
    code = "instance_not_found"


class InstanceUnauthorized(DomainError):
    """Secreto inexistente, vencido o mal formado: un solo código, sin pistas."""

    code = "instance_unauthorized"


class InstanceRevoked(DomainError):
    code = "instance_revoked"


class InstanceRepository(Protocol):
    async def add(self, instance: Instance) -> None: ...

    async def get_by_id(self, instance_id: UUID) -> Instance | None: ...

    async def get_for_update(self, instance_id: UUID) -> Instance | None:
        """Como `get_by_id`, bloqueando la fila (`SELECT ... FOR UPDATE`)."""
        ...

    async def get_by_secret_hash(self, secret_hash: bytes) -> Instance | None:
        """Instancia cuyo secreto actual **o** anterior tiene ese hash (sin validar vigencia)."""
        ...

    async def list_by_client(self, client_id: UUID) -> list[Instance]: ...

    async def save(self, instance: Instance) -> None:
        """Persiste los campos mutables (estado, secretos, huella y último heartbeat)."""
        ...


class HeartbeatRepository(Protocol):
    async def add(self, instance_id: UUID, received_at: datetime, payload: dict[str, Any]) -> None:
        """Guarda el heartbeat completo. Retención de 30 días: job diario pendiente (E4)."""
        ...
