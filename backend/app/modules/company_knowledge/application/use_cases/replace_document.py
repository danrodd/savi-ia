import hashlib
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from app.infrastructure.config.settings import Settings
from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
)
from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentFileTooLargeError,
    CompanyDocumentNotFoundError,
    DuplicateCompanyDocumentError,
)
from app.modules.company_knowledge.domain.interfaces import (
    DocumentIndex,
    DocumentRepository,
    MediaTypeSniffer,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
)


class ReplaceCompanyDocumentUseCase:
    """Reemplaza el archivo de un documento y lo vuelve a encolar."""

    def __init__(
        self,
        repository: DocumentRepository,
        sniffer: MediaTypeSniffer,
        settings: Settings,
        enqueue_notifier: Callable[[], None] | None = None,
        index: DocumentIndex | None = None,
    ) -> None:
        self._repository = repository
        self._sniffer = sniffer
        self._settings = settings
        self._enqueue_notifier = enqueue_notifier
        self._index = index

    async def execute(self, document_id: UUID, *, filename: str, content: bytes) -> CompanyDocument:
        document = await self._repository.get_by_id(document_id)
        if document is None or document.is_deleted:
            raise CompanyDocumentNotFoundError(str(document_id))

        max_bytes = self._settings.company_docs_max_file_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise CompanyDocumentFileTooLargeError(self._settings.company_docs_max_file_mb)

        media_type = self._sniffer.sniff(content, filename)
        sha256 = hashlib.sha256(content).hexdigest()
        existing = await self._repository.get_by_sha256(sha256)
        if existing is not None and existing.id != document_id:
            raise DuplicateCompanyDocumentError(str(existing.id), existing.title)

        document.version += 1
        document.media_type = media_type
        document.original_filename = Path(filename).name
        document.size_bytes = len(content)
        document.sha256 = sha256
        document.status = DocumentStatus.PENDING
        document.status_code = None
        document.page_count = None
        document.chunk_count = 0
        document.char_count = 0
        document.embedding_model = None
        document.processed_at = None

        await self._repository.save_blob(document.id, content)
        await self._repository.delete_chunks(document.id)
        saved = await self._repository.save(document)
        # Los fragmentos viejos ya no representan el archivo: fuera del
        # índice ya, sin esperar a que termine el reproceso.
        if self._index is not None:
            await self._index.remove_document(document.id)
        if self._enqueue_notifier is not None:
            self._enqueue_notifier()
        return saved
