from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.modules.cloud_link.application.cursors import REREAD_WINDOW, start_cursor
from app.modules.cloud_link.application.heartbeat_payload import HeartbeatPayloadBuilder
from app.modules.cloud_link.domain.interfaces import (
    CloudLinkRepository,
    EventSource,
    JsonObject,
    SnapshotSource,
)


@dataclass(frozen=True, slots=True)
class PayloadPreview:
    heartbeat: JsonObject
    # Un evento real por stream, exactamente como viajaría (`null` si el
    # stream no tiene nada pendiente).
    events: dict[str, JsonObject | None] = field(default_factory=dict[str, JsonObject | None])


class PreviewPayloadUseCase:
    """Pantalla de transparencia: qué se envía, antes de que se envíe.

    Usa los mismos extractores y la misma regla de cursor que el ciclo de
    envío, así que el evento mostrado es el primero que viajaría.
    """

    def __init__(
        self,
        repository: CloudLinkRepository,
        payload_builder: HeartbeatPayloadBuilder,
        sources: Sequence[EventSource],
        snapshots: Sequence[SnapshotSource] = (),
        *,
        now: Callable[[], datetime],
        reread_window: timedelta = REREAD_WINDOW,
    ) -> None:
        self._repository = repository
        self._payload_builder = payload_builder
        self._sources = sources
        self._snapshots = snapshots
        self._now = now
        self._reread_window = reread_window

    async def execute(self) -> PayloadPreview:
        state = await self._repository.get()
        heartbeat = await self._payload_builder.build(state)

        events: dict[str, JsonObject | None] = {}
        for source in self._sources:
            watermark = await self._repository.get_watermark(source.stream.value)
            batch = await source.read_batch(start_cursor(watermark, self._reread_window), 1)
            events[source.stream.value] = batch[0].to_payload() if batch else None
        for snapshot in self._snapshots:
            inventory = await snapshot.snapshot(self._now())
            events[snapshot.stream.value] = inventory[0].to_payload() if inventory else None
        return PayloadPreview(heartbeat=heartbeat, events=events)
