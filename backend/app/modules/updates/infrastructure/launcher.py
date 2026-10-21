"""Lanzamiento del instalador de Inno Setup en modo silencioso.

Con `runas`, Windows muestra el cartel de UAC: es el caso de las
instalaciones por máquina (Program Files), que son todas hasta la v1.3.x. Una
instalación por usuario (fase U2 de la spec) se lanza sin elevación.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from app.modules.updates.domain.exceptions import UpdateError
from app.modules.updates.domain.interfaces import InstallerLauncher

# Mismas opciones que la spec 09, sección 4. `/CLOSEAPPLICATIONS` cierra SAVI
# y la entrada `[Run]` sin `skipifsilent` lo vuelve a abrir.
_SILENT_FLAGS = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS"
_SW_HIDE = 0
# ShellExecute devuelve un valor > 32 si salió bien; 5 es acceso denegado, que
# es lo que devuelve cuando la persona cancela el cartel de UAC.
_SE_ERR_ACCESSDENIED = 5


def installed_per_machine(executable: Path) -> bool:
    """SAVI está en Program Files: reemplazarlo pide administrador."""
    # Windows no distingue mayúsculas en las variables de entorno.
    roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")]
    resolved = executable.resolve()
    return any(root and resolved.is_relative_to(Path(root).resolve()) for root in roots)


def silent_parameters(log_path: Path) -> str:
    return f'{_SILENT_FLAGS} /LOG="{log_path}"'


class WindowsInstallerLauncher(InstallerLauncher):
    def __init__(self, *, elevate: bool, log_path: Path) -> None:
        self._elevate = elevate
        self._log_path = log_path

    def launch(self, installer: Path) -> None:
        if sys.platform != "win32":
            raise UpdateError("La actualización automática solo funciona en Windows.")
        verb = "runas" if self._elevate else "open"
        result = int(
            ctypes.windll.shell32.ShellExecuteW(
                None, verb, str(installer), silent_parameters(self._log_path), None, _SW_HIDE
            )
        )
        if result == _SE_ERR_ACCESSDENIED:
            raise UpdateError(
                "Se canceló el permiso de administrador. Sin él no se puede actualizar SAVI."
            )
        if result <= 32:
            raise UpdateError(f"Windows no pudo abrir el instalador (código {result}).")
