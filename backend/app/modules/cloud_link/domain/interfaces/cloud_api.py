from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.modules.cloud_link.domain.entities import CloudNotice
from app.modules.cloud_link.domain.value_objects import SyncPolicy

JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class EnrollResult:
    instance_id: UUID
    instance_secret: str
    client_code: str
    client_name: str
    policy: SyncPolicy


@dataclass(frozen=True, slots=True)
class HeartbeatResult:
    instance_status: str
    policy: SyncPolicy
    notices: list[CloudNotice] = field(default_factory=list[CloudNotice])


@dataclass(frozen=True, slots=True)
class RejectedEvent:
    source_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class IngestResult:
    accepted: int
    duplicates: int
    rejected: list[RejectedEvent] = field(default_factory=list[RejectedEvent])

    @property
    def stored_nothing(self) -> bool:
        """Cloud con la instancia suspendida responde `accepted = 0` sin
        guardar nada ni informar duplicados: la marca no debe avanzar."""
        return self.accepted == 0 and self.duplicates == 0 and not self.rejected


class CloudApi(ABC):
    """Puerto hacia SAVI Cloud (`/api/v1`). Todo error llega como
    `CloudApiError`."""

    @abstractmethod
    async def enroll(self, *, cloud_url: str, token: str, instance: JsonObject) -> EnrollResult: ...

    @abstractmethod
    async def heartbeat(
        self, *, cloud_url: str, secret: str, payload: JsonObject
    ) -> HeartbeatResult: ...

    @abstractmethod
    async def ingest(
        self,
        *,
        cloud_url: str,
        secret: str,
        batch_id: str,
        sent_at: datetime,
        events: Sequence[JsonObject],
    ) -> IngestResult: ...

    @abstractmethod
    async def rotate(self, *, cloud_url: str, secret: str) -> str:
        """Devuelve el secreto nuevo."""
