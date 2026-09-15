from uuid import UUID

from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentNotFoundError,
)
from app.modules.company_knowledge.domain.interfaces import (
    DocumentIndex,
    DocumentRepository,
)


class DeleteCompanyDocumentUseCase:
    """Baja lógica de un documento y su retiro del índice."""

    def __init__(
        self,
        repository: DocumentRepository,
        index: DocumentIndex | None = None,
    ) -> None:
        self._repository = repository
        self._index = index

    async def execute(self, document_id: UUID) -> None:
        deleted = await self._repository.soft_delete(document_id)
        if not deleted:
            # Idempotente como `DELETE /conversations`: eliminar dos veces no
            # es un error, pero un id que nunca existió sí es 404.
            if await self._repository.get_by_id(document_id) is None:
                raise CompanyDocumentNotFoundError(str(document_id))
            return
        if self._index is not None:
            await self._index.remove_document(document_id)
