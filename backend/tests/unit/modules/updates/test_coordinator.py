"""Coordinador: qué ve cada equipo y cómo avanza una actualización.

Puertos falsos: lo que se prueba es el orden (descargar, verificar, esperar
los turnos, lanzar) y que una falla deje SAVI usable.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.modules.updates.application.coordinator import ApplyPhase, UpdateCoordinator
from app.modules.updates.domain.exceptions import (
    InstallerIntegrityError,
    NoUpdateAvailableError,
    UpdateError,
    UpdateInProgressError,
)
from app.modules.updates.domain.interfaces import (
    ActiveTurns,
    InstallerDownloader,
    InstallerLauncher,
    ManifestSource,
)
from app.modules.updates.domain.value_objects import ReleaseManifest, ReleaseVersion, UpdateState

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


def _manifest(version: str = "v1.4.0", min_version: str = "v1.3.1") -> ReleaseManifest:
    return ReleaseManifest.from_mapping(
        {
            "version": version,
            "published_at": "2026-11-02T15:00:00Z",
            "url": f"https://updates.example.com/savi/releases/SAVI-Setup-{version}.exe",
            "sha256": "a" * 64,
            "size": 10,
            "min_version": min_version,
            "min_version_from": "2026-11-05T15:00:00Z",
            "notes": "Novedades.",
        }
    )


class FakeSource(ManifestSource):
    def __init__(self, manifest: ReleaseManifest | None = None) -> None:
        self.manifest = manifest
        self.error: UpdateError | None = None

    async def fetch(self) -> ReleaseManifest:
        if self.error is not None:
            raise self.error
        assert self.manifest is not None
        return self.manifest


class FakeDownloader(InstallerDownloader):
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.release = asyncio.Event()
        self.release.set()

    async def download(self, manifest: ReleaseManifest, on_progress: Callable[[int], None]) -> Path:
        await self.release.wait()
        on_progress(manifest.size)
        if self.error is not None:
            raise self.error
        return Path("SAVI-Setup.exe")


class FakeLauncher(InstallerLauncher):
    def __init__(self) -> None:
        self.launched: list[Path] = []
        self.error: UpdateError | None = None

    def launch(self, installer: Path) -> None:
        if self.error is not None:
            raise self.error
        self.launched.append(installer)


class FakeTurns(ActiveTurns):
    def __init__(self, counts: list[int] | None = None) -> None:
        self.counts = counts or [0]

    def count(self) -> int:
        return self.counts.pop(0) if len(self.counts) > 1 else self.counts[0]


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def _coordinator(
    current: str = "v1.3.2",
    *,
    source: FakeSource | None = None,
    downloader: FakeDownloader | None = None,
    launcher: FakeLauncher | None = None,
    turns: FakeTurns | None = None,
    clock: Clock | None = None,
) -> UpdateCoordinator:
    return UpdateCoordinator(
        current=ReleaseVersion.parse(current),
        source=source or FakeSource(_manifest()),
        downloader=downloader or FakeDownloader(),
        launcher=launcher or FakeLauncher(),
        turns=turns or FakeTurns(),
        clock=clock or Clock(),
        turn_poll_seconds=0.001,
        turn_wait_max_seconds=0.01,
    )


async def test_before_any_check_it_reports_up_to_date() -> None:
    snapshot = _coordinator().snapshot()
    assert snapshot.decision.state is UpdateState.UP_TO_DATE
    assert snapshot.checked_at is None


async def test_check_keeps_the_last_good_manifest_when_the_server_fails() -> None:
    source = FakeSource(_manifest())
    coordinator = _coordinator(source=source)
    await coordinator.check()
    source.error = UpdateError("sin red")
    await coordinator.check()
    assert coordinator.snapshot().decision.state is UpdateState.RECOMMENDED


async def test_deadline_passing_between_checks_blocks_without_a_new_check() -> None:
    clock = Clock()
    coordinator = _coordinator("v1.3.0", clock=clock)
    await coordinator.check()
    assert coordinator.snapshot().decision.state is UpdateState.REQUIRED

    clock.now = NOW + timedelta(days=4)
    assert coordinator.snapshot().decision.state is UpdateState.BLOCKED


async def test_apply_without_a_newer_version_is_rejected() -> None:
    coordinator = _coordinator("v1.4.0")
    await coordinator.check()
    with pytest.raises(NoUpdateAvailableError):
        coordinator.start_apply()


async def test_apply_downloads_verifies_and_launches() -> None:
    launcher = FakeLauncher()
    coordinator = _coordinator(launcher=launcher)
    await coordinator.check()

    await coordinator.start_apply()

    snapshot = coordinator.snapshot()
    assert snapshot.phase is ApplyPhase.INSTALLING
    assert snapshot.downloaded_bytes == 10
    assert launcher.launched == [Path("SAVI-Setup.exe")]


async def test_apply_waits_for_chat_turns_to_finish() -> None:
    launcher = FakeLauncher()
    coordinator = _coordinator(launcher=launcher, turns=FakeTurns([1, 1, 0]))
    await coordinator.check()
    await coordinator.start_apply()
    assert launcher.launched


async def test_apply_gives_up_if_turns_never_finish() -> None:
    launcher = FakeLauncher()
    coordinator = _coordinator(launcher=launcher, turns=FakeTurns([1]))
    await coordinator.check()
    await coordinator.start_apply()

    snapshot = coordinator.snapshot()
    assert snapshot.phase is ApplyPhase.FAILED
    assert snapshot.apply_error is not None
    assert launcher.launched == []


async def test_corrupted_download_fails_with_a_readable_message() -> None:
    downloader = FakeDownloader()
    downloader.error = InstallerIntegrityError("SHA-256 distinto")
    launcher = FakeLauncher()
    coordinator = _coordinator(downloader=downloader, launcher=launcher)
    await coordinator.check()
    await coordinator.start_apply()

    snapshot = coordinator.snapshot()
    assert snapshot.phase is ApplyPhase.FAILED
    assert snapshot.apply_error == (
        "La descarga no coincide con la versión publicada. Intente de nuevo."
    )
    assert launcher.launched == []


async def test_cancelled_uac_is_reported_and_can_be_retried() -> None:
    launcher = FakeLauncher()
    launcher.error = UpdateError("Se canceló el permiso de administrador.")
    coordinator = _coordinator(launcher=launcher)
    await coordinator.check()
    await coordinator.start_apply()
    assert coordinator.snapshot().apply_error == "Se canceló el permiso de administrador."

    launcher.error = None
    await coordinator.start_apply()
    assert coordinator.snapshot().phase is ApplyPhase.INSTALLING


async def test_unexpected_errors_do_not_escape() -> None:
    downloader = FakeDownloader()
    downloader.error = RuntimeError("disco lleno")
    coordinator = _coordinator(downloader=downloader)
    await coordinator.check()
    await coordinator.start_apply()
    assert coordinator.snapshot().phase is ApplyPhase.FAILED


async def test_a_second_apply_while_downloading_is_rejected() -> None:
    downloader = FakeDownloader()
    downloader.release.clear()
    coordinator = _coordinator(downloader=downloader)
    await coordinator.check()
    task = coordinator.start_apply()
    with pytest.raises(UpdateInProgressError):
        coordinator.start_apply()
    downloader.release.set()
    await task
