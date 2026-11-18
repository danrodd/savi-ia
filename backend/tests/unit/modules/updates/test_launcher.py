"""Lanzador: arranca el vigilante y, si no puede, vuelve al método directo."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.modules.updates.domain.exceptions import UpdateError
from app.modules.updates.domain.value_objects import InstallAttempt, ReleaseVersion
from app.modules.updates.infrastructure import launcher as launcher_module
from app.modules.updates.infrastructure.launcher import WindowsInstallerLauncher

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Es el lanzador de Windows.")

ATTEMPT = InstallAttempt(
    attempt_id="a1",
    from_version=ReleaseVersion.parse("v1.3.2"),
    to_version=ReleaseVersion.parse("v1.4.0"),
    started_at=datetime(2026, 11, 2, 15, 0, tzinfo=UTC),
)


class _Process:
    def __init__(self, *, exits_with: int | None) -> None:
        self._exits_with = exits_with

    def wait(self, timeout: float) -> int:
        if self._exits_with is None:
            raise subprocess.TimeoutExpired("powershell", timeout)
        return self._exits_with


@pytest.fixture
def direct(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Registra los lanzamientos directos, sin ejecutar nada."""
    launched: list[Path] = []
    monkeypatch.setattr(
        WindowsInstallerLauncher,
        "_launch_direct",
        lambda self, installer, log_path: launched.append(installer),
    )
    return launched


def _launcher(tmp_path: Path) -> WindowsInstallerLauncher:
    return WindowsInstallerLauncher(
        elevate=True,
        updates_dir=tmp_path / "updates",
        app_exe=tmp_path / "SAVI.exe",
        health_host="127.0.0.1",
        port_from=31900,
    )


def _popen(
    monkeypatch: pytest.MonkeyPatch, process: _Process | None, calls: list[list[str]] | None = None
) -> None:
    def fake(command: list[str], **_: object) -> _Process:
        if calls is not None:
            calls.append(command)
        if process is None:
            raise OSError("no se pudo")
        return process

    monkeypatch.setattr(launcher_module.subprocess, "Popen", fake)


def test_a_running_watcher_means_no_direct_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, direct: list[Path]
) -> None:
    calls: list[list[str]] = []
    _popen(monkeypatch, _Process(exits_with=None), calls)

    _launcher(tmp_path).launch(tmp_path / "SAVI-Setup-v1.4.0.exe", ATTEMPT)

    assert direct == []
    assert "-Elevate" in calls[0]
    assert (tmp_path / "updates" / "watch-install.ps1").is_file()


def test_a_watcher_that_ended_cleanly_is_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, direct: list[Path]
) -> None:
    # Por ejemplo, la persona canceló el permiso enseguida.
    _popen(monkeypatch, _Process(exits_with=0))

    _launcher(tmp_path).launch(tmp_path / "SAVI-Setup-v1.4.0.exe", ATTEMPT)

    assert direct == []


def test_a_watcher_that_could_not_run_falls_back_to_the_direct_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, direct: list[Path]
) -> None:
    _popen(monkeypatch, _Process(exits_with=1))

    _launcher(tmp_path).launch(tmp_path / "SAVI-Setup-v1.4.0.exe", ATTEMPT)

    assert direct == [tmp_path / "SAVI-Setup-v1.4.0.exe"]


def test_powershell_that_cannot_be_started_falls_back_to_the_direct_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, direct: list[Path]
) -> None:
    _popen(monkeypatch, None)

    _launcher(tmp_path).launch(tmp_path / "SAVI-Setup-v1.4.0.exe", ATTEMPT)

    assert direct == [tmp_path / "SAVI-Setup-v1.4.0.exe"]


def test_old_install_logs_are_pruned_before_a_new_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, direct: list[Path]
) -> None:
    updates = tmp_path / "updates"
    updates.mkdir()
    for number in range(9):
        (updates / f"install-{number}.log").write_text("x", encoding="utf-8")
    _popen(monkeypatch, _Process(exits_with=None))

    _launcher(tmp_path).launch(tmp_path / "SAVI-Setup-v1.4.0.exe", ATTEMPT)

    assert len(list(updates.glob("install-*.log"))) == 4


def test_the_direct_launch_still_reports_a_cancelled_permission(tmp_path: Path) -> None:
    class _Shell:
        @staticmethod
        def ShellExecuteW(*_: object) -> int:  # noqa: N802 — nombre de la API de Windows
            return 5

    class _Windll:
        shell32 = _Shell()

    import ctypes

    original = getattr(ctypes, "windll", None)
    ctypes.windll = _Windll()  # type: ignore[attr-defined]
    try:
        with pytest.raises(UpdateError, match="permiso de administrador"):
            _launcher(tmp_path)._launch_direct(  # pyright: ignore[reportPrivateUsage]
                tmp_path / "SAVI-Setup-v1.4.0.exe", tmp_path / "install.log"
            )
    finally:
        ctypes.windll = original  # type: ignore[attr-defined]
