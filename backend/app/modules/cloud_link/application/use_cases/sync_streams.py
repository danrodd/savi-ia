"""Ciclo de envío de eventos (§5.3).

Garantías que sostiene este caso de uso:

- **Keyset `(created_at, id)`**: nunca un `OFFSET` ni un `>=` a secas, que con
  más filas del mismo `created_at` que el tamaño del lote no avanzan.
- **La marca solo avanza con un lote aceptado**, y nunca hacia atrás. Si un
  lote falla, la marca queda donde la dejó el último aceptado.
- **Relectura**: cada ciclo vuelve 15 minutos atrás de la marca; Cloud
  deduplica por `(instance_id, source_id)`.
- **Mismo `batch_id` en el reintento**: el lote que falló se recuerda y, si el
  siguiente ciclo lo reconstruye igual, se reenvía con el mismo id.
- **Nada de contenido**: lo garantizan los extractores (`EventSource`).
"""

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import uuid4

from app.modules.cloud_link.application.cursors import REREAD_WINDOW, start_cursor
from app.modules.cloud_link.application.link_failures import (
    CONTRACT_REJECTED,
    record_cloud_failure,
)
from app.modules.cloud_link.domain.entities import (
    EPOCH,
    CloudLinkState,
    Cursor,
    StreamWatermark,
    SyncEvent,
)
from app.modules.cloud_link.domain.exceptions import CloudApiError
from app.modules.cloud_link.domain.interfaces import (
    CloudApi,
    CloudLinkRepository,
    EventSource,
    SnapshotSource,
)
from app.modules.cloud_link.domain.value_objects import MIN_BATCH_EVENTS, SyncPolicy

logger = logging.getLogger(__name__)

# El inventario de bases se reenvía aunque no cambie, una vez por día.
SNAPSHOT_REFRESH = timedelta(hours=24)


@dataclass(slots=True)
class SyncCycleResult:
    skipped_reason: str | None = None
    batches: int = 0
    events_sent: int = 0
    # El ciclo se cortó (red, 5xx, 401, suspensión): no tiene sentido seguir
    # con los otros streams.
    aborted: bool = False
    retry_after_seconds: float | None = None
    # Streams que quedaron sin enviar por un fallo, con el código.
    stream_errors: dict[str, str] = field(default_factory=dict[str, str])

    @property
    def ok(self) -> bool:
        return self.skipped_reason is None and not self.aborted and not self.stream_errors


@dataclass(frozen=True, slots=True)
class _PendingBatch:
    after: Cursor
    batch_id: str
    digest: str


def _digest(events: Sequence[SyncEvent]) -> str:
    joined = "|".join(e.source_id for e in events)
    return hashlib.sha256(joined.encode()).hexdigest()


class SyncStreamsUseCase:
    def __init__(
        self,
        repository: CloudLinkRepository,
        cloud_api: CloudApi,
        sources: Sequence[EventSource],
        snapshots: Sequence[SnapshotSource] = (),
        *,
        now: Callable[[], datetime],
        new_batch_id: Callable[[], str] = lambda: str(uuid4()),
        reread_window: timedelta = REREAD_WINDOW,
    ) -> None:
        self._repository = repository
        self._cloud_api = cloud_api
        self._sources = sources
        self._snapshots = snapshots
        self._now = now
        self._new_batch_id = new_batch_id
        self._reread_window = reread_window
        self._pending: dict[str, _PendingBatch] = {}
        # Tamaño de lote reducido por un 413, por stream. Se conserva entre
        # ciclos: volver al máximo repetiría el mismo 413 cada cinco minutos.
        self._batch_limits: dict[str, int] = {}

    async def execute(self) -> SyncCycleResult:
        state = await self._repository.get()
        policy = state.effective_policy
        if not state.status.syncs or not state.has_credentials:
            return SyncCycleResult(skipped_reason="not_syncing")
        if not policy.sync_enabled:
            return SyncCycleResult(skipped_reason="sync_disabled_by_cloud")

        result = SyncCycleResult()
        for source in self._sources:
            if await self._sync_incremental(state, source, policy, result):
                break
        if not result.aborted:
            for snapshot in self._snapshots:
                if await self._sync_snapshot(state, snapshot, policy, result):
                    break

        if result.ok:
            now = self._now()

            def mutate(s: CloudLinkState) -> None:
                s.last_attempt_at = now
                s.consecutive_failures = 0
                # Un ciclo completo prueba que Cloud responde y acepta el
                # contrato: cualquier error anterior ya no aplica.
                s.last_error_code = None

            await self._repository.update(mutate)
        return result

    # ── streams incrementales ────────────────────────────────────────────

    async def _sync_incremental(
        self,
        state: CloudLinkState,
        source: EventSource,
        policy: SyncPolicy,
        result: SyncCycleResult,
    ) -> bool:
        """Sincroniza un stream. Devuelve `True` si hay que cortar el ciclo."""
        stream = source.stream.value
        watermark = await self._repository.get_watermark(stream)
        base = watermark or StreamWatermark(stream, EPOCH, "")
        max_seen = Cursor(base.at, base.id)
        pending = self._pending.get(stream)
        cursor = (
            pending.after if pending is not None else start_cursor(watermark, self._reread_window)
        )
        limit = self._limit_for(stream, policy)

        while True:
            events = await source.read_batch(cursor, limit)
            if not events:
                break

            digest = _digest(events)
            pending = self._pending.get(stream)
            reuse = pending is not None and pending.after == cursor and pending.digest == digest
            batch_id = pending.batch_id if reuse and pending is not None else self._new_batch_id()

            try:
                response = await self._cloud_api.ingest(
                    cloud_url=state.cloud_url,
                    secret=state.secret or "",
                    batch_id=batch_id,
                    sent_at=self._now(),
                    events=[e.to_payload() for e in events],
                )
            except CloudApiError as error:
                if error.status_code == 413 and limit > MIN_BATCH_EVENTS:
                    limit = max(MIN_BATCH_EVENTS, limit // 2)
                    self._batch_limits[stream] = limit
                    self._pending.pop(stream, None)
                    continue
                self._pending[stream] = _PendingBatch(cursor, batch_id, digest)
                return await self._on_failure(error, stream, result)

            self._pending.pop(stream, None)
            if response.stored_nothing:
                # Instancia suspendida del lado de Cloud: no guardó nada, así
                # que la marca no se mueve y no se insiste con otros streams.
                result.aborted = True
                result.stream_errors[stream] = "not_stored"
                return True
            if response.rejected:
                logger.warning(
                    "Cloud rechazó %d eventos de %s (%s).",
                    len(response.rejected),
                    stream,
                    ", ".join(sorted({r.reason for r in response.rejected})),
                )

            result.batches += 1
            result.events_sent += len(events)
            cursor = events[-1].cursor
            if cursor.key > max_seen.key:
                max_seen = cursor
            await self._repository.save_watermark(
                StreamWatermark(stream, max_seen.at, max_seen.id, base.last_ok_at)
            )

        await self._repository.save_watermark(
            StreamWatermark(stream, max_seen.at, max_seen.id, self._now())
        )
        return False

    def _limit_for(self, stream: str, policy: SyncPolicy) -> int:
        reduced = self._batch_limits.get(stream)
        if reduced is None:
            return policy.max_batch_events
        return min(reduced, policy.max_batch_events)

    # ── snapshot (inventario de bases) ───────────────────────────────────

    async def _sync_snapshot(
        self,
        state: CloudLinkState,
        source: SnapshotSource,
        policy: SyncPolicy,
        result: SyncCycleResult,
    ) -> bool:
        stream = source.stream.value
        now = self._now()
        events = await source.snapshot(now)
        watermark = await self._repository.get_watermark(stream)
        # El hash deja afuera `last_connection_ok_at`: cambia en cada
        # conexión y volvería "distinto" al inventario en cada ciclo.
        stable = [{k: v for k, v in e.data.items() if k != "last_connection_ok_at"} for e in events]
        inventory = hashlib.sha256(
            json.dumps(stable, sort_keys=True, default=str).encode()
        ).hexdigest()

        unchanged = watermark is not None and watermark.id == inventory
        fresh = watermark is not None and now - watermark.at < SNAPSHOT_REFRESH
        if not events or (unchanged and fresh):
            if watermark is not None:
                await self._repository.save_watermark(
                    StreamWatermark(stream, watermark.at, watermark.id, now)
                )
            return False

        limit = self._limit_for(stream, policy)
        for offset in range(0, len(events), limit):
            chunk = events[offset : offset + limit]
            digest = _digest(chunk)
            pending = self._pending.get(stream)
            reuse = pending is not None and pending.digest == digest
            batch_id = pending.batch_id if reuse and pending is not None else self._new_batch_id()
            try:
                response = await self._cloud_api.ingest(
                    cloud_url=state.cloud_url,
                    secret=state.secret or "",
                    batch_id=batch_id,
                    sent_at=now,
                    events=[e.to_payload() for e in chunk],
                )
            except CloudApiError as error:
                self._pending[stream] = _PendingBatch(Cursor(EPOCH, ""), batch_id, digest)
                return await self._on_failure(error, stream, result)
            self._pending.pop(stream, None)
            if response.stored_nothing:
                result.aborted = True
                result.stream_errors[stream] = "not_stored"
                return True
            result.batches += 1
            result.events_sent += len(chunk)

        await self._repository.save_watermark(StreamWatermark(stream, now, inventory, now))
        return False

    # ── errores ──────────────────────────────────────────────────────────

    async def _on_failure(self, error: CloudApiError, stream: str, result: SyncCycleResult) -> bool:
        """Aplica la regla de §5.6. Devuelve `True` si hay que cortar el ciclo."""
        now = self._now()
        result.stream_errors[stream] = error.error_code
        result.retry_after_seconds = error.retry_after_seconds

        if error.status_code in (413, 422):
            # El sobre no pasa el contrato (o ni el lote mínimo entra): es un
            # defecto nuestro, no de la red. Se detiene ESTE stream sin mover
            # su marca y se deja visible en Administración.
            code = CONTRACT_REJECTED if error.status_code == 422 else error.error_code
            logger.error("Cloud rechazó el lote de %s (%s).", stream, code)

            def mutate(s: CloudLinkState) -> None:
                s.last_attempt_at = now
                s.last_error_code = code[:64]

            await self._repository.update(mutate)
            return False

        updated = await record_cloud_failure(self._repository, error, now, from_heartbeat=False)
        logger.warning(
            "Falló el envío de %s a SAVI Cloud (%s); estado %s.",
            stream,
            error.error_code,
            updated.status.value,
        )
        result.aborted = True
        return True

    @property
    def pending_streams(self) -> frozenset[str]:
        return frozenset(self._pending)
