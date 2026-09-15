from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.company_knowledge.domain.value_objects import (
    DocumentStatus,
    DocumentStatusCode,
    DocumentVisibility,
)


@dataclass(frozen=True, slots=True)
class CompanyDocumentDTO:
    id: UUID
    title: str
    original_filename: str
    media_type: str
    size_bytes: int
    version: int
    status: DocumentStatus
    status_code: DocumentStatusCode | None
    status_message: str | None
    page_count: int | None
    chunk_count: int
    char_count: int
    embedding_model: str | None
    visibility: DocumentVisibility
    modules: list[str]
    all_databases: bool
    database_ids: list[UUID]
    uploaded_by_login: str
    uploaded_by_database_id: UUID | None
    uploaded_by_user_id: int
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CompanyDocumentUsageDTO:
    total: int
    by_status: dict[str, int]
    chunks: int
    chunk_limit: int
    bytes_stored: int
    estimated_index_memory_bytes: int
    embedding_model: str
    documents_awaiting_reindex: int
    index: dict[str, object] | None
