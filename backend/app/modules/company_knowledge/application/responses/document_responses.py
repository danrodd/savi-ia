from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.company_knowledge.application.dtos import (
    CompanyDocumentDTO,
    CompanyDocumentUsageDTO,
)
from app.modules.company_knowledge.application.use_cases.document_access import (
    SearchTestResult,
)
from app.modules.company_knowledge.domain.services import format_pages
from app.modules.company_knowledge.infrastructure.progress import (
    get_progress_registry,
)


class CompanyDocumentResponse(BaseModel):
    id: UUID
    title: str
    original_filename: str
    media_type: str
    size_bytes: int
    version: int
    status: str
    status_code: str | None
    status_message: str | None
    page_count: int | None
    chunk_count: int
    # Avance del procesamiento en curso: `None` salvo mientras se procesa.
    # Vive en memoria del proceso, no en la base (ver `infrastructure/progress.py`).
    progress_done: int | None = None
    progress_total: int | None = None
    char_count: int
    embedding_model: str | None
    visibility: str
    modules: list[str]
    all_databases: bool
    database_ids: list[UUID]
    uploaded_by_login: str
    uploaded_by_database_id: UUID | None
    uploaded_by_user_id: int
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(cls, dto: CompanyDocumentDTO) -> "CompanyDocumentResponse":
        # El avance vive en memoria del proceso y no en el DTO: se consulta
        # acá, al armar la respuesta, y es `None` salvo mientras se procesa.
        progress = get_progress_registry().get(dto.id)
        return cls(
            id=dto.id,
            title=dto.title,
            original_filename=dto.original_filename,
            media_type=dto.media_type,
            size_bytes=dto.size_bytes,
            version=dto.version,
            status=dto.status.value,
            status_code=dto.status_code.value if dto.status_code else None,
            status_message=dto.status_message,
            page_count=dto.page_count,
            chunk_count=dto.chunk_count,
            progress_done=progress.done if progress else None,
            progress_total=progress.total if progress else None,
            char_count=dto.char_count,
            embedding_model=dto.embedding_model,
            visibility=dto.visibility.value,
            modules=dto.modules,
            all_databases=dto.all_databases,
            database_ids=dto.database_ids,
            uploaded_by_login=dto.uploaded_by_login,
            uploaded_by_database_id=dto.uploaded_by_database_id,
            uploaded_by_user_id=dto.uploaded_by_user_id,
            processed_at=dto.processed_at,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


class CompanyDocumentUsageResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    chunks: int
    chunk_limit: int
    bytes_stored: int
    estimated_index_memory_bytes: int
    embedding_model: str
    documents_awaiting_reindex: int
    index: dict[str, object] | None

    @classmethod
    def from_dto(cls, dto: CompanyDocumentUsageDTO) -> "CompanyDocumentUsageResponse":
        return cls(
            total=dto.total,
            by_status=dto.by_status,
            chunks=dto.chunks,
            chunk_limit=dto.chunk_limit,
            bytes_stored=dto.bytes_stored,
            estimated_index_memory_bytes=dto.estimated_index_memory_bytes,
            embedding_model=dto.embedding_model,
            documents_awaiting_reindex=dto.documents_awaiting_reindex,
            index=dto.index,
        )


class SearchTestContextResponse(BaseModel):
    login: str
    has_access: bool
    modules: list[str]
    is_admin: bool


class SearchTestHitResponse(BaseModel):
    document_id: UUID
    title: str
    pages: str | None
    heading: str | None
    snippet: str
    vector_score: float
    bm25_score: float
    rrf_score: float


class ExcludedDocumentResponse(BaseModel):
    document_id: UUID
    title: str
    reason: str


class SearchTestResponse(BaseModel):
    context: SearchTestContextResponse
    results: list[SearchTestHitResponse]
    excluded_documents: list[ExcludedDocumentResponse]

    @classmethod
    def from_result(cls, result: SearchTestResult) -> "SearchTestResponse":
        return cls(
            context=SearchTestContextResponse(
                login=result.context.login,
                has_access=result.context.has_access,
                modules=list(result.context.modules),
                is_admin=result.context.is_admin,
            ),
            results=[
                SearchTestHitResponse(
                    document_id=hit.document_id,
                    title=hit.title,
                    pages=format_pages([(hit.page_from, hit.page_to)]),
                    heading=hit.heading,
                    snippet=hit.text[:400],
                    vector_score=round(hit.vector_score, 4),
                    bm25_score=round(hit.bm25_score, 4),
                    rrf_score=round(hit.rrf_score, 5),
                )
                for hit in result.results
            ],
            excluded_documents=[
                ExcludedDocumentResponse(
                    document_id=doc.document_id, title=doc.title, reason=doc.reason
                )
                for doc in result.excluded_documents
            ],
        )
