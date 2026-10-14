"""Recepción de lotes de eventos (§3.3). No abre transacciones: lo hace el llamador."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.modules.clients.domain import ClientRepository, IdentityMode
from app.modules.ingest.domain import IngestOutcome, IngestRepository
from app.modules.instances.domain import Instance, InstanceStatus
from app.shared.clock import Clock
from app.shared.sync_v1 import (
    EVENT_MODELS,
    AnyEvent,
    IngestRequest,
    RejectedEvent,
    SessionEvent,
)

_MAX_SOURCE_ID = 128


def _source_id_of(raw: dict[str, Any]) -> str:
    value = raw.get("source_id")
    return value[:_MAX_SOURCE_ID] if isinstance(value, str) else ""


def validate_events(
    raw_events: list[dict[str, Any]],
) -> tuple[list[AnyEvent], list[RejectedEvent]]:
    """Separa los eventos válidos de los rechazados; un inválido no afecta al resto."""
    valid: list[AnyEvent] = []
    rejected: list[RejectedEvent] = []
    for raw in raw_events:
        schema = raw.get("schema")
        model = EVENT_MODELS.get(schema) if isinstance(schema, str) else None
        if model is None:
            rejected.append(RejectedEvent(source_id=_source_id_of(raw), reason="unknown_schema"))
            continue
        try:
            valid.append(model.model_validate(raw))
        except ValidationError:
            rejected.append(RejectedEvent(source_id=_source_id_of(raw), reason="invalid_event"))
    return valid, rejected


def _strip_labels(events: list[AnyEvent]) -> list[AnyEvent]:
    out: list[AnyEvent] = []
    for event in events:
        if isinstance(event, SessionEvent) and event.data.user_label is not None:
            event = event.model_copy(
                update={"data": event.data.model_copy(update={"user_label": None})}
            )
        out.append(event)
    return out


class IngestBatchUseCase:
    def __init__(
        self,
        ingest: IngestRepository,
        clock: Clock,
        clients: ClientRepository | None = None,
    ) -> None:
        self._ingest = ingest
        self._clock = clock
        self._clients = clients

    async def execute(self, instance: Instance, request: IngestRequest) -> IngestOutcome:
        if instance.status is not InstanceStatus.ACTIVE:
            # Suspendida: nada se guarda ni se registra el lote, así la instancia lo reenvía
            # completo cuando la reactiven (la marca de agua no avanza, §5.4).
            return IngestOutcome()

        batch_id = UUID(request.batch_id)
        previous = await self._ingest.claim_batch(instance.id, batch_id, self._clock())
        if previous is not None:
            return previous

        valid, rejected = validate_events(request.events)
        valid = await self._without_unauthorized_labels(instance, valid)
        inserted = await self._ingest.insert_events(instance.id, instance.client_id, valid)
        outcome = IngestOutcome(
            accepted=inserted, duplicates=len(valid) - inserted, rejected=rejected
        )
        await self._ingest.complete_batch(instance.id, batch_id, outcome)
        return outcome

    async def _without_unauthorized_labels(
        self, instance: Instance, events: list[AnyEvent]
    ) -> list[AnyEvent]:
        """Defensa en profundidad: una etiqueta de persona solo se guarda si el cliente
        está en modo `named`. Una instancia mal configurada (o vieja) no puede forzar que
        Cloud guarde códigos de usuario de un cliente que no lo autorizó."""
        client = await self._clients.get_by_id(instance.client_id) if self._clients else None
        if client is not None and client.identity_mode is IdentityMode.NAMED:
            return events
        return _strip_labels(events)
