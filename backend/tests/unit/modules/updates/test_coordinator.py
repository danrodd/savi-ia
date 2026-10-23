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
    InstallHistory,
    InstallResultReader,
    ManifestSource,
)
from app.modules.updates.domain.value_objects import (
    InstallAttempt,
    InstallOutcome,
    InstallRecord,
    InstallResult,
    ReleaseManifest,
    ReleaseVersion,
    UpdateState,
    WatcherStep,
)

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
        self.attempts: list[InstallAttempt] = []
        self.error: UpdateError | None = None

    def launch(self, installer: Path, attempt: InstallAttempt) -> None:
        if self.error is not None:
            raise self.error
        self.launched.append(installer)
        self.attempts.append(attempt)


class FakeResults(InstallResultReader):
    """Lo que escribiría el vigilante para el último intento lanzado."""

    def __init__(self, launcher: FakeLauncher) -> None:
        self._launcher = launcher
        self.step: WatcherStep | None = None
        self.exit_code: int | None = None
        self.attempt_id: str | None = None

    def read(self) -> InstallResult | None:
        if self.step is None or not self._launcher.attempts:
            return None
        attempt = self._launcher.attempts[-1]
        return InstallResult(
            attempt_id=self.attempt_id or attempt.attempt_id,
            from_version=attempt.from_version,
            to_version=attempt.to_version,
            started_at=attempt.started_at,
            step=self.step,
            exit_code=self.exit_code,
            finished_at=NOW,
        )


class FakeHistory(InstallHistory):
    def __init__(self) -> None:
        self.records: list[InstallRecord] = []

    def append(self, record: InstallRecord) -> None:
        self.records.append(record)

    def recent(self, limit: int) -> list[InstallRecord]:
        return list(reversed(self.records))[:limit]


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
    results: FakeResults | None = None,
    history: FakeHistory | None = None,
    turns: FakeTurns | None = None,
    clock: Clock | None = None,
) -> UpdateCoordinator:
    launcher = launcher or FakeLauncher()
    return UpdateCoordinator(
        current=ReleaseVersion.parse(current),
        source=source or FakeSource(_manifest()),
        downloader=downloader or FakeDownloader(),
        launcher=launcher,
        results=results or FakeResults(launcher),
        history=history or FakeHistory(),
        turns=turns or FakeTurns(),
        clock=clock or Clock(),
        turn_poll_seconds=0.001,
        turn_wait_max_seconds=0.01,
        install_poll_seconds=0.001,
        install_watch_max_seconds=0.02,
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


# ---------------------------------------------------------- resultado del vigilante


async def _applied(
    *,
    step: WatcherStep | None,
    exit_code: int | None = None,
    attempt_id: str | None = None,
    history: FakeHistory | None = None,
) -> UpdateCoordinator:
    launcher = FakeLauncher()
    results = FakeResults(launcher)
    results.step, results.exit_code, results.attempt_id = step, exit_code, attempt_id
    coordinator = _coordinator(launcher=launcher, results=results, history=history)
    await coordinator.check()
    await coordinator.start_apply()
    return coordinator


async def test_a_cancelled_administrator_permission_fails_and_is_recorded() -> None:
    history = FakeHistory()
    coordinator = await _applied(step=WatcherStep.CANCELLED, history=history)

    snapshot = coordinator.snapshot()
    assert snapshot.phase is ApplyPhase.FAILED
    assert snapshot.apply_error is not None
    assert "permiso de administrador" in snapshot.apply_error
    assert snapshot.last_install is not None
    assert snapshot.last_install.outcome is InstallOutcome.CANCELLED
    assert [record.outcome for record in history.records] == [InstallOutcome.CANCELLED]


async def test_an_installer_that_failed_explains_why_and_keeps_the_current_version() -> None:
    coordinator = await _applied(step=WatcherStep.FAILED, exit_code=4)

    snapshot = coordinator.snapshot()
    assert snapshot.phase is ApplyPhase.FAILED
    assert snapshot.apply_error is not None
    assert "la instalación falló" in snapshot.apply_error
    assert "SAVI sigue en v1.3.2" in snapshot.apply_error
    assert snapshot.last_install is not None
    assert snapshot.last_install.exit_code == 4


async def test_an_installer_that_ended_but_left_the_old_version_is_a_failure() -> None:
    coordinator = await _applied(step=WatcherStep.FINISHED, exit_code=0)

    snapshot = coordinator.snapshot()
    assert snapshot.phase is ApplyPhase.FAILED
    assert snapshot.last_install is not None
    assert snapshot.last_install.outcome is InstallOutcome.ROLLED_BACK


async def test_while_the_watcher_has_not_finished_the_phase_stays_installing() -> None:
    history = FakeHistory()
    coordinator = await _applied(step=WatcherStep.STARTED, history=history)

    assert coordinator.snapshot().phase is ApplyPhase.INSTALLING
    assert history.records == []


async def test_a_result_from_another_attempt_is_ignored() -> None:
    history = FakeHistory()
    coordinator = await _applied(step=WatcherStep.FAILED, attempt_id="otro", history=history)

    assert coordinator.snapshot().phase is ApplyPhase.INSTALLING
    assert history.records == []


async def test_a_new_attempt_after_a_failure_starts_clean() -> None:
    launcher = FakeLauncher()
    results = FakeResults(launcher)
    results.step = WatcherStep.CANCELLED
    coordinator = _coordinator(launcher=launcher, results=results)
    await coordinator.check()
    await coordinator.start_apply()
    assert coordinator.snapshot().phase is ApplyPhase.FAILED

    results.step = None
    await coordinator.start_apply()

    assert coordinator.snapshot().phase is ApplyPhase.INSTALLING
    assert coordinator.snapshot().apply_error is None
    assert len(launcher.attempts) == 2
    assert launcher.attempts[0].attempt_id != launcher.attempts[1].attempt_id


async def test_startup_settles_the_attempt_the_watcher_left() -> None:
    launcher = FakeLauncher()
    results = FakeResults(launcher)
    history = FakeHistory()
    # El intento corrió en el proceso anterior; este es el nuevo, ya en v1.4.0.
    old = _coordinator("v1.3.2", launcher=launcher, results=results)
    results.step = WatcherStep.STARTED
    await old.check()
    await old.start_apply()
    results.step = WatcherStep.FINISHED
    results.exit_code = 0

    new = _coordinator("v1.4.0", launcher=launcher, results=results, history=history)
    record = new.settle_previous_install()

    assert record is not None
    assert record.outcome is InstallOutcome.INSTALLED
    assert new.snapshot().last_install == record
    # Una segunda vez no repite el aviso.
    assert new.settle_previous_install() is None
    assert len(history.records) == 1
