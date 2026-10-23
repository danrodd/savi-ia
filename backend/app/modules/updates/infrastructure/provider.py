"""Singleton de proceso de las actualizaciones y su chequeo periódico.

Mismo patrón que `company_knowledge/infrastructure/provider.py`: se arma en el
`lifespan` y se lee con un getter. Queda desactivado, con el motivo en el log,
si la versión no es un tag exacto (desarrollo), si no hay `UPDATE_URL` o si no
hay clave pública incrustada.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from app._version import __version__
from app.infrastructure.config.settings import Settings
from app.modules.chat.infrastructure.http.turn_registry import get_turn_registry
from app.modules.updates.application.coordinator import UpdateCoordinator
from app.modules.updates.domain.interfaces import ActiveTurns
from app.modules.updates.domain.value_objects import InstallOutcome, ReleaseVersion
from app.modules.updates.infrastructure.http_source import (
    HttpInstallerDownloader,
    HttpManifestSource,
)
from app.modules.updates.infrastructure.install_files import (
    HISTORY_FILENAME,
    RESULT_FILENAME,
    FileInstallHistory,
    FileInstallResultReader,
    delete_downloaded_installers,
)
from app.modules.updates.infrastructure.launcher import (
    WindowsInstallerLauncher,
    installed_per_machine,
)
from app.modules.updates.infrastructure.signing import load_public_keys
from app.modules.updates.infrastructure.trust import DEFAULT_UPDATE_URL, UPDATE_PUBLIC_KEYS
from app.paths import data_dir

log = logging.getLogger(__name__)

_coordinator: UpdateCoordinator | None = None
_loop_task: asyncio.Task[None] | None = None
_cleanup_task: asyncio.Task[None] | None = None

# Segundos entre intentos de borrar el instalador, mientras el suyo termina de cerrarse.
CLEANUP_RETRY_DELAYS: tuple[float, ...] = (5.0, 10.0, 20.0, 40.0)


class _ChatTurns(ActiveTurns):
    def count(self) -> int:
        return get_turn_registry().active_count()


def get_update_coordinator() -> UpdateCoordinator | None:
    return _coordinator


def update_url(settings: Settings) -> str:
    """`UPDATE_URL` del `.env` si está; si no, el servidor oficial."""
    return settings.update_url.strip() or DEFAULT_UPDATE_URL.strip()


def build_coordinator(
    settings: Settings, *, version: str, public_keys_b64: Sequence[str]
) -> UpdateCoordinator | None:
    current = ReleaseVersion.from_running(version)
    if current is None:
        log.info("Actualizaciones desactivadas: %s no es una versión publicada.", version)
        return None
    base_url = update_url(settings)
    if not base_url:
        log.info("Actualizaciones desactivadas: no hay servidor de actualizaciones.")
        return None
    public_keys = load_public_keys(public_keys_b64)
    if not public_keys:
        log.warning("Actualizaciones desactivadas: SAVI no trae la clave pública de SEO.")
        return None

    updates_dir = data_dir() / "updates"
    return UpdateCoordinator(
        current=current,
        source=HttpManifestSource(
            base_url=base_url, channel=settings.update_channel, public_keys=public_keys
        ),
        downloader=HttpInstallerDownloader(target_dir=updates_dir),
        launcher=WindowsInstallerLauncher(
            elevate=installed_per_machine(Path(sys.executable)),
            updates_dir=updates_dir,
            app_exe=Path(sys.executable),
            # 0.0.0.0 no es una dirección a la que se pueda llamar.
            health_host="127.0.0.1"
            if settings.app_host in ("0.0.0.0", "::")
            else settings.app_host,
            port_from=settings.app_port,
        ),
        results=FileInstallResultReader(updates_dir / RESULT_FILENAME),
        history=FileInstallHistory(updates_dir / HISTORY_FILENAME),
        turns=_ChatTurns(),
    )


async def start_updates(settings: Settings) -> None:
    global _coordinator, _loop_task, _cleanup_task
    _coordinator = build_coordinator(
        settings, version=__version__, public_keys_b64=UPDATE_PUBLIC_KEYS
    )
    if _coordinator is None:
        return
    log.info(
        "Actualizaciones: canal %s en %s, cada %s h.",
        settings.update_channel,
        update_url(settings),
        settings.update_check_interval_hours,
    )
    cleanup_pending = await asyncio.to_thread(_settle_previous_install, _coordinator)
    if cleanup_pending:
        _cleanup_task = asyncio.create_task(_delete_installer_when_free())
    _loop_task = asyncio.create_task(
        _check_forever(_coordinator, settings.update_check_interval_hours * 3600)
    )


def _settle_previous_install(coordinator: UpdateCoordinator) -> bool:
    """Cierra el intento de instalación que dejó el vigilante y limpia lo que ya no sirve.

    Devuelve `True` si quedó un instalador por borrar más tarde: SAVI se reabre
    mientras el instalador todavía termina y lo tiene bloqueado.
    """
    try:
        record = coordinator.settle_previous_install()
    except OSError:
        log.exception("Actualizaciones: no se pudo resolver el intento anterior.")
        return False
    if record is None:
        return False
    log.info(
        "Actualizaciones: el intento %s (%s → %s) terminó como %s.",
        record.attempt_id,
        record.from_version,
        record.to_version,
        record.outcome.value,
    )
    if record.outcome is InstallOutcome.INSTALLED:
        # El instalador descargado (unos 160 MB) ya no sirve.
        try:
            delete_downloaded_installers(data_dir() / "updates")
        except OSError:
            return True
    return False


async def _delete_installer_when_free(
    retry_delays: Sequence[float] = CLEANUP_RETRY_DELAYS,
) -> None:
    """Reintenta el borrado hasta que el instalador termine de cerrarse."""
    for delay in retry_delays:
        await asyncio.sleep(delay)
        try:
            await asyncio.to_thread(delete_downloaded_installers, data_dir() / "updates")
        except OSError:
            continue
        return
    log.warning("Actualizaciones: no se pudo borrar el instalador descargado.")


async def stop_updates() -> None:
    global _coordinator, _loop_task, _cleanup_task
    if _cleanup_task is not None:
        _cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _cleanup_task
        _cleanup_task = None
    if _loop_task is not None:
        _loop_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _loop_task
    _loop_task = None
    _coordinator = None


async def _check_forever(coordinator: UpdateCoordinator, interval_seconds: float) -> None:
    while True:
        await coordinator.check()
        await asyncio.sleep(interval_seconds)
