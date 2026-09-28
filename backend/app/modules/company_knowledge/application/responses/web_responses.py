from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.company_knowledge.application.use_cases import (
    WebSourceDetail,
    WebSourcePreview,
)
from app.modules.company_knowledge.domain.entities.web_source import WebPage, WebSource


class WebSourcePreviewResponse(BaseModel):
    url: str
    title: str
    sample: str
    words: int
    page_count: int
    truncated: bool
    used_sitemap: bool
    # Páginas por sección del sitemap ("wp-sitemap-posts-post-1.xml": 17),
    # para que el administrador excluya las que no aportan.
    sections: dict[str, int]
    warnings: list[str]

    @classmethod
    def from_preview(cls, preview: WebSourcePreview) -> "WebSourcePreviewResponse":
        return cls(
            url=preview.url,
            title=preview.title,
            sample=preview.sample,
            words=preview.words,
            page_count=preview.page_count,
            truncated=preview.truncated,
            used_sitemap=preview.used_sitemap,
            sections=preview.sections,
            warnings=preview.warnings,
        )


class WebSourceResponse(BaseModel):
    id: UUID
    url: str
    mode: str
    title: str
    refresh: str
    max_pages: int
    excluded_sections: list[str]
    visibility: str
    modules: list[str]
    all_databases: bool
    database_ids: list[UUID]
    status: str
    status_code: str | None
    status_message: str | None
    page_count: int
    skipped_count: int
    last_crawl_started_at: datetime | None
    last_crawl_finished_at: datetime | None
    next_refresh_at: datetime | None
    created_by_login: str
    created_at: datetime

    @classmethod
    def from_entity(cls, source: WebSource) -> "WebSourceResponse":
        return cls(
            id=source.id,
            url=source.url,
            mode=source.mode.value,
            title=source.title,
            refresh=source.refresh.value,
            max_pages=source.max_pages,
            excluded_sections=source.excluded_sections,
            visibility=source.visibility.value,
            modules=[module.value for module in source.modules],
            all_databases=source.all_databases,
            database_ids=source.database_ids,
            status=source.status.value,
            status_code=source.status_code.value if source.status_code else None,
            status_message=source.status_message,
            page_count=source.page_count,
            skipped_count=source.skipped_count,
            last_crawl_started_at=source.last_crawl_started_at,
            last_crawl_finished_at=source.last_crawl_finished_at,
            next_refresh_at=source.next_refresh_at,
            created_by_login=source.created_by_login,
            created_at=source.created_at,
        )


class WebPageResponse(BaseModel):
    document_id: UUID
    url: str
    title: str
    status: str
    status_detail: str | None
    last_fetched_at: datetime | None
    last_changed_at: datetime | None

    @classmethod
    def from_entity(cls, page: WebPage) -> "WebPageResponse":
        return cls(
            document_id=page.document_id,
            url=page.url,
            title=page.title,
            status=page.status.value,
            status_detail=page.status_detail,
            last_fetched_at=page.last_fetched_at,
            last_changed_at=page.last_changed_at,
        )


class WebSourceDetailResponse(WebSourceResponse):
    pages: list[WebPageResponse]

    @classmethod
    def from_detail(cls, detail: WebSourceDetail) -> "WebSourceDetailResponse":
        base = WebSourceResponse.from_entity(detail.source).model_dump()
        return cls(**base, pages=[WebPageResponse.from_entity(page) for page in detail.pages])
