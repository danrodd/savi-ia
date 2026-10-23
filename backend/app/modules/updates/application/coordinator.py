"""Estado de la actualización en este proceso: qué hay publicado y qué se está haciendo.

Un solo coordinador por proceso (SAVI corre con un worker). Guarda el último
manifiesto verificado y no la decisión: la decisión depende de la hora, y un
plazo de `min_version_from` puede vencer entre dos chequeos.

Cada paso queda en `savi.log` (spec 09, sección 5): chequeo, descarga,
verificación, lanzamiento y resultado.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.modules.updates.application.install_history import reconcile_last_install
from app.modules.updates.domain.exceptions import (
    DowngradeRejectedError,
    InstallerIntegrityError,
    NoUpdateAvailableError,
    UpdateError,
    UpdateInProgressError,
)
from app.modules.updates.domain.interfaces import (
    ActiveTurns,
    InstallerDownloader,
    InstallerLauncher,
    InstallHistory,
    InstallResultReader,
    ManifestSource,
)
from app.modules.updates.domain.value_objects import (
    InstallAttempt,
    InstallOutcome,
    InstallRecord,
    ReleaseManifest,
    ReleaseVersion,
    UpdateDecision,
    UpdateState,
    WatcherStep,
    decide,
    settle,
)

log = logging.getLogger(__name__)

_INTEGRITY_MESSAGE = "La descarga no coincide con la versión publicada. Intente de nuevo."
_GENERIC_MESSAGE = "No se pudo descargar la actualización. Intente de nuevo más tarde."
_BUSY_MESSAGE = (
    "Hay respuestas del asistente en curso desde hace demasiado tiempo. "
    "Intente de nuevo cuando terminen."
)


class ApplyPhase(StrEnum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    # Descargado y verificado; espera a que terminen los turnos del chat.
    WAITING_TURNS = "waiting_turns"
    # El instalador ya corre: en segundos cierra SAVI y lo vuelve a abrir.
    INSTALLING = "installing"
    FAILED = "failed"


@dataclass(frozen=True)
class UpdateSnapshot:
    decision: UpdateDecision
    checked_at: datetime | None
    phase: ApplyPhase
    downloaded_bytes: int
    apply_error: str | None
    # El último intento resuelto (de esta sesión o de una anterior).
    last_install: InstallRecord | None = None


class UpdateCoordinator:
    def __init__(
        self,
        *,
        current: ReleaseVersion,
        source: ManifestSource,
        downloader: InstallerDownloader,
        launcher: InstallerLauncher,
        results: InstallResultReader,
        history: InstallHistory,
        turns: ActiveTurns,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        turn_poll_seconds: float = 2.0,
        turn_wait_max_seconds: float = 600.0,
        install_poll_seconds: float = 2.0,
        # Más que el tope del vigilante (30 min): si el vigilante llegó a su
        # límite, acá todavía se alcanza a leer lo que escribió.
        install_watch_max_seconds: float = 2400.0,
    ) -> None:
        self._current = current
        self._source = source
        self._downloader = downloader
        self._launcher = launcher
        self._results = results
        self._history = history
        self._turns = turns
        self._clock = clock
        self._turn_poll_seconds = turn_poll_seconds
        self._turn_wait_max_seconds = turn_wait_max_seconds
        self._install_poll_seconds = install_poll_seconds
        self._install_watch_max_seconds = install_watch_max_seconds

        self._manifest: ReleaseManifest | None = None
        self._checked_at: datetime | None = None
        self._phase = ApplyPhase.IDLE
        self._downloaded = 0
        self._apply_error: str | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def current(self) -> ReleaseVersion:
        return self._current

    async def check(self) -> None:
        """Lee el manifiesto. Si falla, se conserva el último bueno."""
        try:
            manifest = await self._source.fetch()
        except UpdateError as exc:
            log.warning("Actualizaciones: el chequeo falló: %s", exc)
            return
        self._manifest = manifest
        self._checked_at = self._clock()
        decision = decide(self._current, manifest, self._checked_at)
        log.info(
            "Actualizaciones: instalada %s, publicada %s, mínima %s → %s",
            self._current,
            manifest.version,
            manifest.min_version,
            decision.state,
        )

    def snapshot(self) -> UpdateSnapshot:
        return UpdateSnapshot(
            decision=self._decision(),
            checked_at=self._checked_at,
            phase=self._phase,
            downloaded_bytes=self._downloaded,
            apply_error=self._apply_error,
            last_install=self.last_install(),
        )

    def last_install(self) -> InstallRecord | None:
        recent = self._history.recent(1)
        return recent[0] if recent else None

    def install_history(self, limit: int) -> list[InstallRecord]:
        return self._history.recent(limit)

    def settle_previous_install(self) -> InstallRecord | None:
        """Al arrancar: da por resuelto el intento que dejó el vigilante, si lo hay."""
        return reconcile_last_install(
            results=self._results,
            history=self._history,
            running=self._current,
            now=self._clock(),
        )

    def start_apply(self) -> asyncio.Task[None]:
        """Arranca la descarga e instalación en segundo plano y vuelve enseguida."""
        if self._phase in (ApplyPhase.DOWNLOADING, ApplyPhase.WAITING_TURNS, ApplyPhase.INSTALLING):
            raise UpdateInProgressError()
        decision = self._decision()
        if decision.state is UpdateState.UP_TO_DATE or decision.manifest is None:
            raise NoUpdateAvailableError()
        manifest = decision.manifest
        # `decide` ya lo filtra; se repite acá porque este es el punto donde
        # se ejecuta código, y bajar de versión no se hace nunca.
        if manifest.version <= self._current:
            raise DowngradeRejectedError(
                f"El manifiesto ofrece {manifest.version} y está instalada {self._current}."
            )
        self._phase = ApplyPhase.DOWNLOADING
        self._downloaded = 0
        self._apply_error = None
        self._task = asyncio.create_task(self._apply(manifest))
        return self._task

    async def _apply(self, manifest: ReleaseManifest) -> None:
        log.info("Actualizaciones: descargando %s desde %s", manifest.version, manifest.url)
        try:
            installer = await self._downloader.download(manifest, self._on_progress)
            log.info("Actualizaciones: %s descargado y verificado (SHA-256).", installer.name)

            self._phase = ApplyPhase.WAITING_TURNS
            if not await self._wait_for_idle_chat():
                self._fail(_BUSY_MESSAGE, "quedaron turnos del chat en curso")
                return

            self._phase = ApplyPhase.INSTALLING
            attempt = InstallAttempt(
                attempt_id=uuid.uuid4().hex,
                from_version=self._current,
                to_version=manifest.version,
                started_at=self._clock(),
            )
            # Puede bloquear unos segundos (arranque del vigilante): fuera del event loop.
            await asyncio.to_thread(self._launcher.launch, installer, attempt)
            log.info(
                "Actualizaciones: instalador de %s lanzado (intento %s).",
                manifest.version,
                attempt.attempt_id,
            )
            await self._watch_install(attempt)
        except InstallerIntegrityError as exc:
            self._fail(_INTEGRITY_MESSAGE, str(exc))
        except UpdateError as exc:
            self._fail(str(exc) or _GENERIC_MESSAGE, str(exc))
        except Exception as exc:  # noqa: BLE001 — cualquier falla deja SAVI usable
            log.exception("Actualizaciones: error inesperado")
            self._fail(_GENERIC_MESSAGE, repr(exc))

    async def _wait_for_idle_chat(self) -> bool:
        waited = 0.0
        while self._turns.count() > 0:
            if waited >= self._turn_wait_max_seconds:
                return False
            await asyncio.sleep(self._turn_poll_seconds)
            waited += self._turn_poll_seconds
        return True

    async def _watch_install(self, attempt: InstallAttempt) -> None:
        """Mientras SAVI siga vivo, lee lo que escribe el vigilante.

        Si el instalador cierra SAVI, esta tarea muere con el proceso y el
        resultado lo recoge el SAVI nuevo al arrancar. Acá solo se llega a
        saber de las instalaciones que NO cerraron SAVI: el permiso de
        administrador cancelado, o un instalador que no pudo arrancar.
        """
        waited = 0.0
        while waited < self._install_watch_max_seconds:
            await asyncio.sleep(self._install_poll_seconds)
            waited += self._install_poll_seconds
            result = self._results.read()
            if (
                result is None
                or result.attempt_id != attempt.attempt_id
                or result.step is WatcherStep.STARTED
            ):
                continue
            record = settle(result, self._current, self._clock())
            self._remember(record)
            if record.outcome is not InstallOutcome.INSTALLED:
                self._fail(record.message, f"{record.outcome}, código {result.exit_code}")
            return
        log.warning(
            "Actualizaciones: el vigilante no informó el resultado de %s.", attempt.attempt_id
        )

    def _remember(self, record: InstallRecord) -> None:
        try:
            self._history.append(record)
        except OSError:
            log.exception("Actualizaciones: no se pudo guardar el historial.")
        log.info(
            "Actualizaciones: intento %s terminó como %s.", record.attempt_id, record.outcome.value
        )

    def _on_progress(self, downloaded: int) -> None:
        self._downloaded = downloaded

    def _fail(self, message: str, detail: str) -> None:
        log.error("Actualizaciones: falló la actualización: %s", detail)
        self._phase = ApplyPhase.FAILED
        self._apply_error = message

    def _decision(self) -> UpdateDecision:
        if self._manifest is None:
            return UpdateDecision(UpdateState.UP_TO_DATE, self._current)
        return decide(self._current, self._manifest, self._clock())
