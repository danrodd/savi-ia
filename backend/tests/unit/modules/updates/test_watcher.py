"""Vigilante de la instalación.

Los de forma se prueban en cualquier sistema. Los de comportamiento corren el
PowerShell real con un "instalador" y un "SAVI" falsos (un `.cmd` y un servidor
HTTP en un hilo), solo en Windows. Lo que no se puede probar sin una persona es
el cartel del permiso de administrador: queda en la prueba real de la Fase 2.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.modules.updates.domain.value_objects import (
    InstallOutcome,
    InstallResult,
    ReleaseVersion,
    WatcherStep,
    settle,
)
from app.modules.updates.infrastructure.install_files import FileInstallResultReader
from app.modules.updates.infrastructure.watcher import (
    POWERSHELL_FLAGS,
    WATCHER_SCRIPT,
    WatcherJob,
    watcher_command,
    write_script,
)

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Necesita PowerShell de Windows.")


def _job(tmp_path: Path, **overrides: object) -> WatcherJob:
    params: dict[str, object] = {
        "installer": tmp_path / "SAVI-Setup-v1.4.0.exe",
        "installer_flags": "/VERYSILENT /SUPPRESSMSGBOXES",
        "log_path": tmp_path / "install-a1.log",
        "app_exe": tmp_path / "SAVI.exe",
        "result_path": tmp_path / "last-install.json",
        "attempt_id": "a1",
        "from_version": "v1.3.2",
        "to_version": "v1.4.0",
        "health_host": "127.0.0.1",
        "port_from": 31900,
        "port_count": 20,
        "elevate": False,
    }
    params.update(overrides)
    return WatcherJob(**params)  # type: ignore[arg-type]


# ------------------------------------------------------------------- de forma


def test_the_script_is_ascii_only() -> None:
    # PowerShell 5.1 lee un archivo sin BOM con la página de códigos del
    # sistema: una letra con tilde en el script se corrompería.
    assert WATCHER_SCRIPT.isascii()


def test_a_cancelled_permission_is_read_from_the_windows_error_code() -> None:
    # Con Start-Process el cartel cancelado llega como un error sin codigo y con
    # el texto en el idioma de Windows: se marcaba "failed" y no "cancelled".
    # Process.Start deja el 1223 en una excepcion interna, que hay que recorrer.
    assert "Start-Process -FilePath $Installer" not in WATCHER_SCRIPT
    assert "[System.Diagnostics.Process]::Start($info)" in WATCHER_SCRIPT
    assert "$problem = $problem.InnerException" in WATCHER_SCRIPT
    assert "$native -eq 1223" in WATCHER_SCRIPT


def test_the_command_passes_every_value_as_its_own_argument(tmp_path: Path) -> None:
    command = watcher_command(Path("watch.ps1"), _job(tmp_path))

    assert command[0].lower().endswith("powershell.exe")
    assert tuple(command[1 : 1 + len(POWERSHELL_FLAGS)]) == POWERSHELL_FLAGS
    start = 1 + len(POWERSHELL_FLAGS)
    pairs = dict(zip(command[start::2], command[start + 1 :: 2], strict=False))
    assert pairs["-File"] == "watch.ps1"
    assert pairs["-InstallerFlags"] == "/VERYSILENT /SUPPRESSMSGBOXES"
    assert pairs["-AttemptId"] == "a1"
    assert pairs["-PortFrom"] == "31900"
    assert "-Elevate" not in command


def test_elevation_is_a_switch_only_when_needed(tmp_path: Path) -> None:
    assert watcher_command(Path("w.ps1"), _job(tmp_path, elevate=True))[-1] == "-Elevate"


def test_the_script_is_written_with_windows_line_endings(tmp_path: Path) -> None:
    script = write_script(tmp_path / "updates")

    assert script.read_bytes().count(b"\r\n") == WATCHER_SCRIPT.count("\n")


# ---------------------------------------------------------- PowerShell de verdad


class _SaviStub:
    """Un "SAVI" que responde `/health`, cuando se lo permite."""

    def __init__(self, version: str = "v1.4.0") -> None:
        self.ready = threading.Event()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if not stub.ready.is_set():
                    self.send_response(503)
                    self.end_headers()
                    return
                body = json.dumps({"status": "ok", "version": version}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = int(self.server.server_address[1])


@contextmanager
def _savi_stub(*, up: bool = True, version: str = "v1.4.0") -> Iterator[_SaviStub]:
    stub = _SaviStub(version)
    if up:
        stub.ready.set()
    thread = threading.Thread(target=stub.server.serve_forever, daemon=True)
    thread.start()
    try:
        yield stub
    finally:
        stub.server.shutdown()
        stub.server.server_close()


def _run_watcher(
    tmp_path: Path,
    stub: _SaviStub,
    *,
    installer_body: str | None,
    install_timeout: int = 60,
    health_timeout: int = 3,
) -> tuple[InstallResult, Path]:
    # Con espacios y una ñ a propósito: así quedan las carpetas de muchos usuarios.
    folder = tmp_path / "Carpeta con espacios y ñ"
    folder.mkdir()
    installer = folder / "SAVI-Setup-v1.4.0.cmd"
    if installer_body is not None:
        installer.write_text(f"@echo off\r\n{installer_body}\r\n", encoding="utf-8")
    app = folder / "SAVI.cmd"
    marker = folder / "relanzado.txt"
    # Relativo a su propia carpeta: un .cmd no lee bien una ñ escrita en UTF-8.
    app.write_text('@echo off\r\necho abierto> "%~dp0relanzado.txt"\r\n', encoding="utf-8")
    job = _job(
        folder,
        installer=installer,
        app_exe=app,
        port_from=stub.port,
        port_count=1,
        install_timeout_seconds=install_timeout,
        health_timeout_seconds=health_timeout,
    )
    script = write_script(folder)
    done = subprocess.run(  # noqa: S603 — comando armado por el propio test
        watcher_command(script, job), capture_output=True, timeout=180, check=False
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    result = FileInstallResultReader(job.result_path).read()
    assert result is not None, "el vigilante no dejó el resultado"
    return result, marker


@windows_only
def test_a_successful_install_is_recorded_without_touching_savi(tmp_path: Path) -> None:
    with _savi_stub() as stub:
        result, marker = _run_watcher(tmp_path, stub, installer_body="exit 0")

    assert result.step is WatcherStep.FINISHED
    assert result.exit_code == 0
    assert result.running_version == "v1.4.0"
    assert result.relaunched is False
    assert not marker.exists()
    assert result.attempt_id == "a1"
    new = ReleaseVersion.parse("v1.4.0")
    assert settle(result, new, datetime.now(UTC)).outcome is InstallOutcome.INSTALLED


@windows_only
def test_a_failed_install_reopens_savi_and_keeps_the_exit_code(tmp_path: Path) -> None:
    with _savi_stub(up=False) as stub:
        result, marker = _run_watcher(tmp_path, stub, installer_body="exit 4")

    assert result.step is WatcherStep.FAILED
    assert result.exit_code == 4
    assert result.relaunched is True
    assert marker.exists(), "no se volvió a abrir SAVI"
    old = ReleaseVersion.parse("v1.3.2")
    assert settle(result, old, datetime.now(UTC)).outcome is InstallOutcome.FAILED


@windows_only
def test_an_installer_that_cannot_start_is_a_failure_without_a_code(tmp_path: Path) -> None:
    with _savi_stub() as stub:
        result, marker = _run_watcher(tmp_path, stub, installer_body=None)

    assert result.step is WatcherStep.FAILED
    assert result.exit_code is None
    # SAVI nunca se cerró: no hay nada que reabrir.
    assert result.relaunched is False
    assert not marker.exists()


@windows_only
def test_an_installer_that_never_ends_is_a_timeout(tmp_path: Path) -> None:
    with _savi_stub() as stub:
        result, _ = _run_watcher(
            tmp_path, stub, installer_body="ping -n 30 127.0.0.1 >nul", install_timeout=2
        )

    assert result.step is WatcherStep.TIMEOUT
    assert result.exit_code is None


@windows_only
def test_savi_started_by_the_installer_is_not_opened_twice(tmp_path: Path) -> None:
    # El instalador termina bien y SAVI tarda unos segundos en responder: es
    # la entrada [Run] del instalador. El vigilante espera y no lo abre.
    with _savi_stub(up=False) as stub:
        threading.Timer(2.0, stub.ready.set).start()
        result, marker = _run_watcher(tmp_path, stub, installer_body="exit 0", health_timeout=30)

    assert result.step is WatcherStep.FINISHED
    assert result.relaunched is False
    assert result.running_version == "v1.4.0"
    assert not marker.exists()


@windows_only
def test_savi_that_never_comes_back_is_reopened_after_a_good_install(tmp_path: Path) -> None:
    with _savi_stub(up=False) as stub:
        result, marker = _run_watcher(tmp_path, stub, installer_body="exit 0", health_timeout=3)

    assert result.step is WatcherStep.FINISHED
    assert result.relaunched is True
    assert marker.exists()
