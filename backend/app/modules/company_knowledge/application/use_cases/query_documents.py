from uuid import UUID

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.application.dtos import CompanyDocumentUsageDTO
from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
)
from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentNotFoundError,
)
from app.modules.company_knowledge.domain.interfaces import (
    DocumentIndex,
    DocumentRepository,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentVisibility,
)


class ListCompanyDocumentsUseCase:
    def __init__(self, repository: DocumentRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        status: DocumentStatus | None = None,
        visibility: DocumentVisibility | None = None,
        module: ModuleCode | None = None,
        database_id: UUID | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CompanyDocument]:
        return await self._repository.list_documents(
            status=status,
            visibility=visibility,
            module=module,
            database_id=database_id,
            query=query,
            limit=limit,
            offset=offset,
        )


class GetCompanyDocumentUseCase:
    def __init__(self, repository: DocumentRepository) -> None:
        self._repository = repository

    async def execute(self, document_id: UUID) -> CompanyDocument:
        document = await self._repository.get_by_id(document_id)
        if document is None or document.is_deleted:
            raise CompanyDocumentNotFoundError(str(document_id))
        return document


class GetCompanyDocumentUsageUseCase:
    """Uso de la instalación: documentos, fragmentos, espacio e índice."""

    def __init__(
        self,
        repository: DocumentRepository,
        *,
        chunk_limit: int,
        embedding_model: str,
        index: DocumentIndex | None = None,
    ) -> None:
        self._repository = repository
        self._chunk_limit = chunk_limit
        self._embedding_model = embedding_model
        self._index = index

    async def execute(self) -> CompanyDocumentUsageDTO:
        by_status = await self._repository.count_by_status()
        chunks = await self._repository.total_chunks()
        index_status = self._index.status() if self._index is not None else None
        index: dict[str, object] | None = None
        if index_status is not None:
            index = {
                "loaded": index_status.loaded,
                "chunks": index_status.chunks,
                "memory_bytes": index_status.memory_bytes,
                "documents_awaiting_reindex": index_status.documents_awaiting_reindex,
            }
        return CompanyDocumentUsageDTO(
            total=sum(by_status.values()),
            by_status={status.value: total for status, total in by_status.items()},
            chunks=chunks,
            chunk_limit=self._chunk_limit,
            bytes_stored=await self._repository.total_bytes_stored(),
            estimated_index_memory_bytes=index_status.memory_bytes if index_status else 0,
            embedding_model=self._embedding_model,
            documents_awaiting_reindex=(
                index_status.documents_awaiting_reindex if index_status else 0
            ),
            index=index,
        )
