from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.company_knowledge.domain.services.document_access_policy import (
    DocumentAccessContext,
)


@dataclass(frozen=True, slots=True)
class ChunkHit:
    document_id: UUID
    title: str
    version: int
    ordinal: int
    text: str
    page_from: int | None = None
    page_to: int | None = None
    heading: str | None = None
    source_url: str | None = None
    vector_score: float = 0.0
    bm25_score: float = 0.0
    rrf_score: float = 0.0


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    """Documento que el usuario puede consultar, sin su contenido."""

    document_id: UUID
    title: str
    version: int
    page_count: int | None = None
    updated_at: datetime | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class IndexStatus:
    loaded: bool
    chunks: int
    memory_bytes: int
    model: str | None
    documents_awaiting_reindex: int = 0


class DocumentIndex(ABC):
    """Índice híbrido en memoria. Fase 2."""

    @abstractmethod
    async def search(
        self, query: str, ctx: DocumentAccessContext, *, limit: int = 6
    ) -> list[ChunkHit]: ...

    @abstractmethod
    async def list_documents(self, ctx: DocumentAccessContext) -> list[IndexedDocument]:
        """Documentos listos que `ctx` puede leer, con el mismo filtro que `search`."""

    @abstractmethod
    async def publish_document(self, document_id: UUID) -> None: ...

    @abstractmethod
    async def update_metadata(self, document_id: UUID) -> None: ...

    @abstractmethod
    async def remove_document(self, document_id: UUID) -> None: ...

    @abstractmethod
    def status(self) -> IndexStatus: ...
