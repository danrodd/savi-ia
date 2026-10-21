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
from pathlib import Path

from app._version import __version__
from app.infrastructure.config.settings import Settings
from app.modules.chat.infrastructure.http.turn_registry import get_turn_registry
from app.modules.updates.application.coordinator import UpdateCoordinator
from app.modules.updates.domain.interfaces import ActiveTurns
from app.modules.updates.domain.value_objects import ReleaseVersion
from app.modules.updates.infrastructure.http_source import (
    HttpInstallerDownloader,
    HttpManifestSource,
)
from app.modules.updates.infrastructure.launcher import (
    WindowsInstallerLauncher,
    installed_per_machine,
)
from app.modules.updates.infrastructure.signing import load_public_key
from app.modules.updates.infrastructure.trust import UPDATE_PUBLIC_KEY
from app.paths import data_dir

log = logging.getLogger(__name__)

_coordinator: UpdateCoordinator | None = None
_loop_task: asyncio.Task[None] | None = None


class _ChatTurns(ActiveTurns):
    def count(self) -> int:
        return get_turn_registry().active_count()


def get_update_coordinator() -> UpdateCoordinator | None:
    return _coordinator


def build_coordinator(
    settings: Settings, *, version: str, public_key_b64: str
) -> UpdateCoordinator | None:
    current = ReleaseVersion.from_running(version)
    if current is None:
        log.info("Actualizaciones desactivadas: %s no es una versión publicada.", version)
        return None
    if not settings.update_url.strip():
        log.info("Actualizaciones desactivadas: falta UPDATE_URL.")
        return None
    public_key = load_public_key(public_key_b64)
    if public_key is None:
        log.warning("Actualizaciones desactivadas: SAVI no trae la clave pública de SEO.")
        return None

    updates_dir = data_dir() / "updates"
    return UpdateCoordinator(
        current=current,
        source=HttpManifestSource(
            base_url=settings.update_url, channel=settings.update_channel, public_key=public_key
        ),
        downloader=HttpInstallerDownloader(target_dir=updates_dir),
        launcher=WindowsInstallerLauncher(
            elevate=installed_per_machine(Path(sys.executable)),
            log_path=updates_dir / "install.log",
        ),
        turns=_ChatTurns(),
    )


async def start_updates(settings: Settings) -> None:
    global _coordinator, _loop_task
    _coordinator = build_coordinator(
        settings, version=__version__, public_key_b64=UPDATE_PUBLIC_KEY
    )
    if _coordinator is None:
        return
    log.info(
        "Actualizaciones: canal %s en %s, cada %s h.",
        settings.update_channel,
        settings.update_url,
        settings.update_check_interval_hours,
    )
    _loop_task = asyncio.create_task(
        _check_forever(_coordinator, settings.update_check_interval_hours * 3600)
    )


async def stop_updates() -> None:
    global _coordinator, _loop_task
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
