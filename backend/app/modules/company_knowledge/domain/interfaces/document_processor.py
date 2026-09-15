from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.modules.company_knowledge.domain.entities.processing import PendingChunk
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
    async def process(self, content: bytes, media_type: str) -> ProcessingOutcome: ...
