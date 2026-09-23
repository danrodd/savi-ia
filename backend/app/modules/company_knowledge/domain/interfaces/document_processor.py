from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID

from app.modules.company_knowledge.domain.entities.processing import (
    ExtractedText,
    PendingChunk,
)
from app.modules.company_knowledge.domain.value_objects.reading import ReadingMethod
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentStatusCode,
)


@dataclass(frozen=True, slots=True)
class ProcessingOutcome:
    """Resultado de procesar un documento: estado final y fragmentos.

    `chunks` solo tiene contenido con `status = READY`. `NO_TEXT` y
    `FAILED` nunca dejan fragmentos parciales.
    """

    status: DocumentStatus
    status_code: DocumentStatusCode | None = None
    page_count: int | None = None
    char_count: int = 0
    embedding_model: str | None = None
    chunks: list[PendingChunk] = field(default_factory=list[PendingChunk])
    # Lectura del PDF (Fase 4). `None` en TXT/Markdown.
    reading_method: ReadingMethod | None = None
    ai_page_count: int = 0
    ai_cost_usd: float | None = None

    @staticmethod
    def failed(code: DocumentStatusCode) -> "ProcessingOutcome":
        return ProcessingOutcome(status=DocumentStatus.FAILED, status_code=code)


class DocumentProcessor(ABC):
    """Extrae, fragmenta y vectoriza un archivo.

    Es trabajo de CPU: la implementación lo corre fuera del event loop.
    Levanta `EmbedderUnavailableError` si el modelo no carga, para que el
    documento vuelva a la cola en lugar de quedar `failed` por un problema
    de la instalación y no del archivo.
    """

    @abstractmethod
    async def process(
        self, content: bytes, media_type: str, document_id: UUID | None = None
    ) -> ProcessingOutcome:
        """Procesa el contenido y devuelve el resultado.

        `document_id` es opcional y solo se usa para reportar avance: los
        tests llaman sin él."""
        ...

    @abstractmethod
    async def process_pages(
        self,
        extracted: ExtractedText,
        document_id: UUID | None = None,
        *,
        detect_scanned: bool = True,
    ) -> ProcessingOutcome:
        """Fragmenta y vectoriza un texto ya extraído.

        Lo usa la lectura de PDF por páginas: la extracción (con `pypdf` o
        con IA) ya ocurrió y aquí solo queda indexar. `detect_scanned`
        aplica el umbral de caracteres por página que delata un escaneo; con
        páginas leídas por la IA se apaga.
        """
        ...
