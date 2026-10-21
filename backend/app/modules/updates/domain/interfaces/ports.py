from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from app.modules.updates.domain.value_objects import ReleaseManifest


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
    def launch(self, installer: Path) -> None:
        """Lanza el instalador en modo silencioso y vuelve enseguida.

        El instalador cierra SAVI, reemplaza los archivos y lo vuelve a abrir.
        """


class ActiveTurns(ABC):
    @abstractmethod
    def count(self) -> int:
        """Turnos del chat en curso: no se actualiza a mitad de una respuesta."""
