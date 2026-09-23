"""Puertos de la lectura de PDF con IA (Fase 4)."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.modules.company_knowledge.domain.entities.page_reading import (
    AiReadRecord,
    AiReadResult,
    KnowledgeSettings,
    PageMetrics,
    PdfAnalysis,
    ReadPage,
)
from app.modules.company_knowledge.domain.value_objects.reading import PageRoute


class PdfPageAnalyzer(ABC):
    """Trabajo local sobre el PDF con `pypdf`. CPU: se corre en el executor."""

    @abstractmethod
    def analyze(self, content: bytes) -> PdfAnalysis:
        """Texto y métricas de cada página.

        Levanta `DocumentExtractionError` si el PDF está cifrado, no se puede
        leer o supera el máximo de páginas: esas reglas no cambian con la IA.
        """

    @abstractmethod
    def measure_pages(self, content: bytes, page_numbers: Sequence[int]) -> dict[int, int]:
        """Bytes de cada página como PDF suelto (base 1).

        Es una cota por arriba del aporte de la página a un tramo: los
        recursos compartidos (fuentes) se cuentan en cada una.
        """

    @abstractmethod
    def build_segments(self, content: bytes, groups: Sequence[Sequence[int]]) -> list[bytes]:
        """Un PDF por grupo, con esas páginas (base 1) en orden."""


class PdfPageReader(ABC):
    """Lee un tramo de PDF con el proveedor de IA. Una implementación por proveedor."""

    @property
    @abstractmethod
    def provider(self) -> str: ...

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    async def read(
        self, segment: bytes, first_page: int, last_page: int, *, attempt: int = 0
    ) -> AiReadResult:
        """Transcribe las páginas `first_page..last_page` (numeración del documento).

        `attempt` > 0 es un reintento: el prompt recuerda el formato. Levanta
        `AiReadingError`, con `retryable` cuando vale la pena reintentar
        (429, 5xx, timeout, JSON inválido).
        """


@dataclass(frozen=True, slots=True)
class AiReaderAvailability:
    """Si hay con qué leer con IA y con qué proveedor y modelo."""

    available: bool
    provider: str | None = None
    model: str | None = None
    credential_kind: str | None = None
    # USD por millón de tokens del modelo de lectura; `None` sin precios.
    input_price: float | None = None
    output_price: float | None = None
    # Motivo legible cuando `available` es falso.
    reason: str | None = None


class AiReaderProvider(ABC):
    """Arma el lector del proveedor activo, que se resuelve en cada documento.

    Cambiar de proveedor o su credencial en administración aplica al
    próximo documento sin reiniciar, igual que el chat.
    """

    @abstractmethod
    async def availability(self) -> AiReaderAvailability: ...

    @abstractmethod
    async def build_reader(self) -> PdfPageReader | None:
        """`None` si no hay un proveedor usable para leer documentos."""


class PageRoutingPolicy(ABC):
    """Decide, página por página, si la lee `pypdf` o la IA."""

    @abstractmethod
    def decide(self, page: PageMetrics) -> PageRoute: ...


class DocumentPageRepository(ABC):
    """Páginas leídas y registro de gasto de la lectura con IA."""

    @abstractmethod
    async def list_pages(self, document_id: UUID, version: int) -> list[ReadPage]: ...

    @abstractmethod
    async def save_pages(self, document_id: UUID, version: int, pages: Sequence[ReadPage]) -> None:
        """Inserta o reemplaza esas páginas de esa versión."""

    @abstractmethod
    async def delete_ai_pages(self, document_id: UUID, version: int) -> None:
        """Descarta lo leído con IA para volver a leerlo ("Leer con IA")."""

    @abstractmethod
    async def delete_other_versions(self, document_id: UUID, keep_version: int) -> None:
        """Las páginas de versiones reemplazadas ya no corresponden a ningún archivo."""

    @abstractmethod
    async def record_ai_read(self, record: AiReadRecord) -> None: ...

    @abstractmethod
    async def ai_cost(self, document_id: UUID, version: int) -> float | None:
        """Suma del costo de la versión; `None` si ningún pedido tuvo precio."""

    @abstractmethod
    async def average_cost_per_page(self, provider: str, model: str) -> float | None:
        """Costo real promedio por página de las lecturas hechas con ese modelo."""


class KnowledgeSettingsRepository(ABC):
    @abstractmethod
    async def get(self) -> KnowledgeSettings:
        """La configuración vigente, o la de fábrica si nunca se guardó."""

    @abstractmethod
    async def save(self, settings: KnowledgeSettings) -> KnowledgeSettings: ...
