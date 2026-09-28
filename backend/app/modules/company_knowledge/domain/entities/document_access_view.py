from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentVisibility,
)


@dataclass(frozen=True, slots=True)
class DocumentAccessView:
    """Subconjunto inmutable del documento que guarda el índice."""

    id: UUID
    status: DocumentStatus
    deleted: bool
    visibility: DocumentVisibility
    modules: frozenset[ModuleCode]
    all_databases: bool
    database_ids: frozenset[UUID]
    title: str = ""
    version: int = 1
    page_count: int | None = None
    updated_at: datetime | None = None
    # Página de un sitio web: se cita con su link.
    source_url: str | None = None

    @staticmethod
    def from_document(
        document: CompanyDocument, database_ids: frozenset[UUID]
    ) -> "DocumentAccessView":
        return DocumentAccessView(
            id=document.id,
            status=document.status,
            deleted=document.is_deleted,
            visibility=document.visibility,
            modules=frozenset(document.modules),
            all_databases=document.all_databases,
            database_ids=database_ids,
            title=document.title,
            version=document.version,
            page_count=document.page_count,
            updated_at=document.updated_at,
            source_url=document.source_url,
        )
