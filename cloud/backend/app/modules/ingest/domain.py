from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.shared.sync_v1 import AnyEvent, RejectedEvent


@dataclass(frozen=True)
class IngestOutcome:
    accepted: int = 0
    duplicates: int = 0
    rejected: list[RejectedEvent] = field(default_factory=list[RejectedEvent])


class IngestRepository(Protocol):
    async def claim_batch(
        self, instance_id: UUID, batch_id: UUID, received_at: datetime
    ) -> IngestOutcome | None:
        """Reserva `(instance_id, batch_id)`.

        Devuelve `None` si el lote es nuevo (queda reservado en la transacción actual) o el
        resultado guardado si ya se procesó: un lote repetido no se reprocesa.
        """
        ...

    async def insert_events(
        self, instance_id: UUID, client_id: UUID, events: Sequence[AnyEvent]
    ) -> int:
        """Inserta con `ON CONFLICT DO NOTHING` y devuelve cuántos eran nuevos."""
        ...

    async def complete_batch(
        self, instance_id: UUID, batch_id: UUID, outcome: IngestOutcome
    ) -> None: ...
