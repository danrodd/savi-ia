from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID


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


class InstanceRepository(Protocol):
    async def add(self, instance: Instance) -> None: ...

    async def list_by_client(self, client_id: UUID) -> list[Instance]: ...
