"""Lanzamiento del instalador de Inno Setup en modo silencioso.

Con el permiso de administrador (UAC) se lanzan las instalaciones por máquina
(Program Files), que son todas hasta la v1.3.x. Una instalación por usuario
(fase U2 de la spec) se lanza sin elevación.

El instalador no se lanza desde SAVI sino desde un vigilante (`watcher.py`): un
proceso aparte que sobrevive al cierre de SAVI, anota cómo terminó la
instalación y reabre SAVI si nadie lo hizo. Si el vigilante no puede arrancar
(por ejemplo, una política que impide PowerShell), se vuelve al método directo:
funciona igual, pero sin recuperación si la instalación falla.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
from pathlib import Path

from app.modules.updates.domain.exceptions import UpdateError
from app.modules.updates.domain.interfaces import InstallerLauncher
from app.modules.updates.domain.value_objects import InstallAttempt
from app.modules.updates.infrastructure.install_files import (
    INSTALL_LOGS_KEPT,
    RESULT_FILENAME,
    install_log_path,
    prune_install_logs,
)
from app.modules.updates.infrastructure.watcher import WatcherJob, watcher_command, write_script

log = logging.getLogger(__name__)

# Mismas opciones que la spec 09, sección 4. `/CLOSEAPPLICATIONS` cierra SAVI
# y la entrada `[Run]` sin `skipifsilent` lo vuelve a abrir.
_SILENT_FLAGS = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS"
_SW_HIDE = 0
# ShellExecute devuelve un valor > 32 si salió bien; 5 es acceso denegado, que
# es lo que devuelve cuando la persona cancela el cartel de UAC.
_SE_ERR_ACCESSDENIED = 5
# Puertos que prueba SAVI al arrancar si el configurado está ocupado
# (`_PORT_SCAN_RANGE` en `app/launcher.py`).
PORT_SCAN_RANGE = 20
# Un vigilante sano sigue corriendo: si sale antes de esto con un error, no pudo arrancar.
_WATCHER_PROBE_SECONDS = 3.0


def installed_per_machine(executable: Path) -> bool:
    """SAVI está en Program Files: reemplazarlo pide administrador."""
    # Windows no distingue mayúsculas en las variables de entorno.
    roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")]
    resolved = executable.resolve()
    return any(root and resolved.is_relative_to(Path(root).resolve()) for root in roots)


def silent_parameters(log_path: Path) -> str:
    return f'{_SILENT_FLAGS} /LOG="{log_path}"'


class WindowsInstallerLauncher(InstallerLauncher):
    def __init__(
        self,
        *,
        elevate: bool,
        updates_dir: Path,
        app_exe: Path,
        health_host: str,
        port_from: int,
    ) -> None:
        self._elevate = elevate
        self._updates_dir = updates_dir
        self._app_exe = app_exe
        self._health_host = health_host
        self._port_from = port_from

    def launch(self, installer: Path, attempt: InstallAttempt) -> None:
        if sys.platform != "win32":
            raise UpdateError("La actualización automática solo funciona en Windows.")
        prune_install_logs(self._updates_dir, keep=INSTALL_LOGS_KEPT - 1)
        log_path = install_log_path(self._updates_dir, attempt.attempt_id)
        job = WatcherJob(
            installer=installer,
            installer_flags=_SILENT_FLAGS,
            log_path=log_path,
            app_exe=self._app_exe,
            result_path=self._updates_dir / RESULT_FILENAME,
            attempt_id=attempt.attempt_id,
            from_version=str(attempt.from_version),
            to_version=str(attempt.to_version),
            health_host=self._health_host,
            port_from=self._port_from,
            port_count=PORT_SCAN_RANGE,
            elevate=self._elevate,
        )
        if self._start_watcher(job):
            return
        log.warning("Actualizaciones: no arrancó el vigilante; se lanza el instalador directo.")
        self._launch_direct(installer, log_path)

    def _start_watcher(self, job: WatcherJob) -> bool:
        try:
            script = write_script(self._updates_dir)
            process = subprocess.Popen(  # noqa: S603 — ruta absoluta del sistema, sin shell
                watcher_command(script, job),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        except OSError:
            log.exception("Actualizaciones: no se pudo arrancar el vigilante.")
            return False
        try:
            code = process.wait(timeout=_WATCHER_PROBE_SECONDS)
        except subprocess.TimeoutExpired:
            return True
        if code == 0:
            return True
        log.warning("Actualizaciones: el vigilante salió con el código %s.", code)
        return False

    def _launch_direct(self, installer: Path, log_path: Path) -> None:
        verb = "runas" if self._elevate else "open"
        result = int(
            ctypes.windll.shell32.ShellExecuteW(
                None, verb, str(installer), silent_parameters(log_path), None, _SW_HIDE
            )
        )
        if result == _SE_ERR_ACCESSDENIED:
            raise UpdateError(
                "Se canceló el permiso de administrador. Sin él no se puede actualizar SAVI."
            )
        if result <= 32:
            raise UpdateError(f"Windows no pudo abrir el instalador (código {result}).")
