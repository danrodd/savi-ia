from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.domain.value_objects.reading import ReadingMethod
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentStatusCode,
    DocumentVisibility,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class CompanyDocument:
    """Documento propio de la empresa con sus metadatos y permisos."""

    id: UUID = field(default_factory=uuid4)
    title: str = ""
    original_filename: str = ""
    media_type: str = ""
    size_bytes: int = 0
    sha256: str = ""
    version: int = 1
    status: DocumentStatus = DocumentStatus.PENDING
    status_code: DocumentStatusCode | None = None
    page_count: int | None = None
    chunk_count: int = 0
    char_count: int = 0
    embedding_model: str | None = None
    # Cómo se leyó (solo PDF): `None` hasta procesarlo o en TXT/Markdown.
    reading_method: ReadingMethod | None = None
    ai_page_count: int = 0
    ai_cost_usd: float | None = None
    visibility: DocumentVisibility = DocumentVisibility.ADMINS
    modules: list[ModuleCode] = field(default_factory=list[ModuleCode])
    all_databases: bool = True
    database_ids: list[UUID] = field(default_factory=list[UUID])
    uploaded_by_login: str = ""
    uploaded_by_database_id: UUID | None = None
    uploaded_by_user_id: int = 0
    processed_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_ready(self) -> bool:
        return self.status == DocumentStatus.READY and not self.is_deleted


@dataclass
class DocumentChunk:
    """Fragmento de un documento con su vector serializado."""

    id: UUID = field(default_factory=uuid4)
    document_id: UUID = field(default_factory=uuid4)
    ordinal: int = 0
    page_from: int | None = None
    page_to: int | None = None
    heading: str | None = None
    text: str = ""
    embedding: bytes = b""
    created_at: datetime = field(default_factory=_utc_now)
