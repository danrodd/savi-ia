"""Tarea de fondo del `lifespan`: heartbeat y ciclo de envío (§5.7).

Reglas:

- Dos bucles independientes: un envío largo (historial grande) no retrasa el
  heartbeat ni hace pasar a la instancia por `offline`.
- Una excepción no controlada en un ciclo se loguea con su stack y el bucle
  **sigue**. Nunca tumba la aplicación (RNF-05).
- El chat no espera nada de esto: son tareas aparte, sin lock compartido con
  los writers del chat, y cada operación usa sus propias sesiones cortas.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.modules.cloud_link.application.backoff import backoff_seconds
from app.modules.cloud_link.domain.value_objects import LinkStatus
from app.modules.cloud_link.infrastructure.composition import CloudLinkServices
from app.modules.cloud_link.infrastructure.startup import link_from_settings

logger = logging.getLogger(__name__)

# Cada cuánto se revisa si hay algo que hacer cuando no hay vinculación.
IDLE_POLL_SECONDS = 60.0
# `unauthorized`: el heartbeat reintenta cada hora por si fue un fallo
# transitorio de Cloud.
UNAUTHORIZED_HEARTBEAT_SECONDS = 3600.0
CRASH_RETRY_SECONDS = 60.0
# Piso de toda espera: un delay en cero convertiría el bucle en un spin.
MIN_WAIT_SECONDS = 1.0


class CloudLinkScheduler:
    def __init__(
        self,
        services: CloudLinkServices,
        *,
        env_path: Path | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._services = services
        self._env_path = env_path
        self._rng = rng
        self._tasks: list[asyncio.Task[None]] = []
        self._wake_events: list[asyncio.Event] = []

    # ── ciclo de vida ────────────────────────────────────────────────────

    def start(self) -> None:
        if self._tasks:
            return
        heartbeat_wake, sync_wake = asyncio.Event(), asyncio.Event()
        self._wake_events = [heartbeat_wake, sync_wake]
        self._services.on_wake = self.wake
        self._tasks = [
            asyncio.create_task(
                self._loop(self.heartbeat_once, heartbeat_wake, "heartbeat", first=self._auto_link),
                name="cloud-link-heartbeat",
            ),
            asyncio.create_task(
                self._loop(self.sync_once, sync_wake, "ingest"), name="cloud-link-ingest"
            ),
        ]

    async def stop(self) -> None:
        tasks, self._tasks = self._tasks, []
        self._services.on_wake = None
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def wake(self) -> None:
        for event in self._wake_events:
            event.set()

    # ── pasos (cada uno devuelve cuánto esperar) ─────────────────────────

    async def heartbeat_once(self) -> float:
        services = self._services
        outcome = await services.heartbeat.execute()
        state = await services.repository.get()
        if not state.status.sends_heartbeat:
            return IDLE_POLL_SECONDS
        if state.status == LinkStatus.UNAUTHORIZED:
            return UNAUTHORIZED_HEARTBEAT_SECONDS
        if outcome.sent and not outcome.ok:
            return backoff_seconds(
                state.consecutive_failures,
                retry_after_seconds=outcome.retry_after_seconds,
                rng=self._rng,
            )
        return float(state.effective_policy.heartbeat_seconds)

    async def sync_once(self) -> float:
        services = self._services
        state = await services.repository.get()
        if not state.status.syncs:
            return IDLE_POLL_SECONDS
        async with services.sync_lock.acquire() as acquired:
            if not acquired:
                return float(state.effective_policy.ingest_seconds)
            result = await services.sync.execute()
        state = await services.repository.get()
        if result.skipped_reason is not None:
            return IDLE_POLL_SECONDS
        if result.aborted and state.consecutive_failures > 0:
            return backoff_seconds(
                state.consecutive_failures,
                retry_after_seconds=result.retry_after_seconds,
                rng=self._rng,
            )
        return float(state.effective_policy.ingest_seconds)

    # ── plomería ─────────────────────────────────────────────────────────

    async def _auto_link(self) -> None:
        if await link_from_settings(self._services, env_path=self._env_path) is not None:
            # Vinculada (o ya lo estaba): que el envío no espere el sondeo.
            self.wake()

    async def _loop(
        self,
        step: Callable[[], Awaitable[float]],
        wake: asyncio.Event,
        name: str,
        *,
        first: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        if first is not None:
            try:
                await first()
            except Exception:
                logger.exception("Falló la vinculación automática con SAVI Cloud.")
        while True:
            # Antes del paso: un `wake()` que llegue mientras corre no se pierde.
            wake.clear()
            try:
                delay = await step()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Falló un ciclo de %s con SAVI Cloud; se sigue.", name)
                delay = CRASH_RETRY_SECONDS
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(wake.wait(), timeout=max(delay, MIN_WAIT_SECONDS))
