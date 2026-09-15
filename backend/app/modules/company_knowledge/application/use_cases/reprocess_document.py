from collections.abc import Callable
from uuid import UUID

from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
)
from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentConflictError,
    CompanyDocumentNotFoundError,
)
from app.modules.company_knowledge.domain.interfaces import (
    DocumentIndex,
    DocumentRepository,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
)


class ReprocessCompanyDocumentUseCase:
    """Devuelve un documento a `pending` para reextraerlo y reindexarlo."""

    def __init__(
        self,
        repository: DocumentRepository,
        enqueue_notifier: Callable[[], None] | None = None,
        index: DocumentIndex | None = None,
    ) -> None:
        self._repository = repository
        self._enqueue_notifier = enqueue_notifier
        self._index = index

    async def execute(self, document_id: UUID) -> CompanyDocument:
        document = await self._repository.get_by_id(document_id)
        if document is None or document.is_deleted:
            raise CompanyDocumentNotFoundError(str(document_id))
        if document.status == DocumentStatus.PROCESSING:
            raise CompanyDocumentConflictError("El documento se está procesando.")

        await self._repository.delete_chunks(document.id)
        document.status = DocumentStatus.PENDING
        document.status_code = None
        document.chunk_count = 0
        saved = await self._repository.save(document)
        if self._index is not None:
            await self._index.remove_document(document.id)
        if self._enqueue_notifier is not None:
            self._enqueue_notifier()
        return saved
