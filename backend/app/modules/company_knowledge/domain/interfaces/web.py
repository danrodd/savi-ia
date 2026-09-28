from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.modules.company_knowledge.domain.entities.web_source import (
    Discovery,
    ExtractedPage,
    FetchResult,
    WebPage,
    WebSource,
)


class WebFetcher(ABC):
    """Descarga con la guarda contra SSRF aplicada en cada conexión.

    Levanta `UnsafeUrlError` si la URL (o una redirección) apunta a la red
    interna, y `WebFetchError` ante errores de red o tiempo.
    """

    @abstractmethod
    async def fetch(
        self, url: str, *, etag: str | None = None, last_modified: str | None = None
    ) -> FetchResult: ...

    @abstractmethod
    async def allowed_by_robots(self, url: str) -> bool: ...

    @abstractmethod
    async def validate(self, url: str) -> None:
        """Aplica la guarda contra SSRF sin descargar (`UnsafeUrlError`)."""


class ContentExtractor(ABC):
    @abstractmethod
    def extract(self, html: str, url: str) -> ExtractedPage:
        """Contenido principal en Markdown (CPU: correr en un executor)."""

    @abstractmethod
    def remove_boilerplate(
        self, pages: dict[str, str], share: float = 0.5
    ) -> tuple[dict[str, str], str]:
        """Quita los bloques repetidos en muchas páginas del sitio.

        Devuelve el Markdown limpio por URL y los bloques quitados, una vez,
        para el documento "Información general del sitio".
        """


class PageDiscoverer(ABC):
    @abstractmethod
    async def discover(
        self, root: str, *, max_pages: int, excluded_sections: Sequence[str]
    ) -> Discovery: ...


class WebSourceRepository(ABC):
    @abstractmethod
    async def save(self, source: WebSource) -> WebSource: ...

    @abstractmethod
    async def get_by_id(self, source_id: UUID) -> WebSource | None: ...

    @abstractmethod
    async def list_sources(self) -> list[WebSource]: ...

    @abstractmethod
    async def count_active(self) -> int: ...

    @abstractmethod
    async def claim_next_due(self) -> WebSource | None:
        """Toma la fuente `pending` más antigua y la marca `crawling`."""

    @abstractmethod
    async def requeue_crawling(self) -> int:
        """Devuelve a `pending` las fuentes que quedaron `crawling` (reinicio)."""

    @abstractmethod
    async def enqueue_due_refreshes(self) -> int:
        """Pasa a `pending` las fuentes `ready`/`failed` con el refresco vencido."""

    @abstractmethod
    async def soft_delete(self, source_id: UUID) -> bool: ...

    @abstractmethod
    async def list_pages(self, source_id: UUID) -> list[WebPage]: ...

    @abstractmethod
    async def save_page(self, page: WebPage) -> None: ...

    @abstractmethod
    async def delete_page(self, document_id: UUID) -> None: ...
