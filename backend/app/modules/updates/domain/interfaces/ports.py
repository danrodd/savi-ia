from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from app.modules.updates.domain.value_objects import (
    InstallAttempt,
    InstallRecord,
    InstallResult,
    ReleaseManifest,
)


class ManifestSource(ABC):
    """El manifiesto publicado del canal, con la firma ya verificada."""

    @abstractmethod
    async def fetch(self) -> ReleaseManifest: ...


class InstallerDownloader(ABC):
    @abstractmethod
    async def download(self, manifest: ReleaseManifest, on_progress: Callable[[int], None]) -> Path:
        """Descarga el instalador y lo verifica contra el manifiesto.

        `on_progress` recibe los bytes acumulados. Devuelve la ruta solo si el
        SHA-256 y el tamaño coinciden.
        """


class InstallerLauncher(ABC):
    @abstractmethod
    def launch(self, installer: Path, attempt: InstallAttempt) -> None:
        """Lanza el instalador en modo silencioso y vuelve enseguida.

        El instalador cierra SAVI y reemplaza los archivos. Un vigilante que
        sobrevive al cierre registra cómo terminó y, si SAVI no volvió a abrir,
        lo abre con la versión que haya quedado instalada.
        """


class InstallResultReader(ABC):
    @abstractmethod
    def read(self) -> InstallResult | None:
        """Lo que escribió el vigilante, o `None` si no hay nada legible."""


class InstallHistory(ABC):
    @abstractmethod
    def append(self, record: InstallRecord) -> None: ...

    @abstractmethod
    def recent(self, limit: int) -> list[InstallRecord]:
        """Los últimos intentos, el más reciente primero."""


class ActiveTurns(ABC):
    @abstractmethod
    def count(self) -> int:
        """Turnos del chat en curso: no se actualiza a mitad de una respuesta."""
