import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import UUID

from app.infrastructure.config.settings import Settings
from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.application.permissions import (
    ensure_databases_exist,
    validate_visibility,
)
from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
)
from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentFileTooLargeError,
    CompanyDocumentIndexLimitReachedError,
    DuplicateCompanyDocumentError,
)
from app.modules.company_knowledge.domain.interfaces import (
    DocumentRepository,
    MediaTypeSniffer,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentVisibility,
)
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository


class UploadCompanyDocumentUseCase:
    """Registra un documento nuevo y encola su procesamiento."""

    def __init__(
        self,
        repository: DocumentRepository,
        sniffer: MediaTypeSniffer,
        settings: Settings,
        erp_repository: ErpDatabaseRepository,
        enqueue_notifier: Callable[[], None] | None = None,
    ) -> None:
        self._repository = repository
        self._sniffer = sniffer
        self._settings = settings
        self._erp_repository = erp_repository
        self._enqueue_notifier = enqueue_notifier

    async def execute(
        self,
        *,
        filename: str,
        content: bytes,
        title: str | None,
        visibility: DocumentVisibility,
        modules: Sequence[ModuleCode],
        all_databases: bool,
        database_ids: Sequence[UUID],
        uploaded_by_login: str,
        uploaded_by_database_id: UUID,
        uploaded_by_user_id: int,
    ) -> CompanyDocument:
        max_bytes = self._settings.company_docs_max_file_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise CompanyDocumentFileTooLargeError(self._settings.company_docs_max_file_mb)

        media_type = self._sniffer.sniff(content, filename)
        sha256 = hashlib.sha256(content).hexdigest()
        existing = await self._repository.get_by_sha256(sha256)
        if existing is not None:
            raise DuplicateCompanyDocumentError(str(existing.id), existing.title)

        validate_visibility(visibility, modules, all_databases, database_ids)
        if not all_databases:
            await ensure_databases_exist(self._erp_repository, database_ids)

        if await self._repository.total_chunks() >= self._settings.company_docs_max_total_chunks:
            raise CompanyDocumentIndexLimitReachedError(
                self._settings.company_docs_max_total_chunks
            )

        clean_title = title.strip() if title and title.strip() else Path(filename).stem
        document = CompanyDocument(
            title=clean_title,
            original_filename=Path(filename).name,
            media_type=media_type,
            size_bytes=len(content),
            sha256=sha256,
            version=1,
            status=DocumentStatus.PENDING,
            visibility=visibility,
            modules=list(modules),
            all_databases=all_databases,
            database_ids=list(database_ids),
            uploaded_by_login=uploaded_by_login,
            uploaded_by_database_id=uploaded_by_database_id,
            uploaded_by_user_id=uploaded_by_user_id,
        )
        await self._repository.save(document)
        await self._repository.save_blob(document.id, content)
        if self._enqueue_notifier is not None:
            self._enqueue_notifier()
        return document
