"""Fuentes web y sus páginas (Fase 5).

Una página importada es un `CompanyDocument` más (`source_kind = web`): el
índice, los permisos y las citas no distinguen. Estas entidades guardan lo
propio de la web: de dónde se lee, cada cuánto y cómo saber si cambió.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.domain.value_objects.visibility import DocumentVisibility
from app.modules.company_knowledge.domain.value_objects.web import (
    RefreshFrequency,
    WebPageStatus,
    WebSourceMode,
    WebSourceStatus,
    WebSourceStatusCode,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class WebSource:
    id: UUID = field(default_factory=uuid4)
    url: str = ""
    mode: WebSourceMode = WebSourceMode.PAGE
    title: str = ""
    refresh: RefreshFrequency = RefreshFrequency.WEEKLY
    max_pages: int = 200
    # Grupos del sitemap que el administrador excluyó (p. ej. las entradas
    # de demostración del tema). Se comparan por prefijo del nombre.
    excluded_sections: list[str] = field(default_factory=list[str])
    visibility: DocumentVisibility = DocumentVisibility.ALL
    modules: list[ModuleCode] = field(default_factory=list[ModuleCode])
    all_databases: bool = True
    database_ids: list[UUID] = field(default_factory=list[UUID])
    status: WebSourceStatus = WebSourceStatus.PENDING
    status_code: WebSourceStatusCode | None = None
    status_message: str | None = None
    page_count: int = 0
    skipped_count: int = 0
    last_crawl_started_at: datetime | None = None
    last_crawl_finished_at: datetime | None = None
    next_refresh_at: datetime | None = None
    created_by_login: str = ""
    created_by_database_id: UUID | None = None
    created_by_user_id: int = 0
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    deleted_at: datetime | None = None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


@dataclass
class WebPage:
    """Una página de la fuente y el documento que la representa."""

    document_id: UUID
    source_id: UUID
    url: str
    title: str = ""
    status: WebPageStatus = WebPageStatus.IMPORTED
    status_detail: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    content_hash: str = ""
    missing_count: int = 0
    last_fetched_at: datetime | None = None
    last_changed_at: datetime | None = None


# ── Resultados de los puertos ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str  # URL final, después de redirecciones validadas
    status_code: int
    content_type: str = ""
    body: bytes = b""
    text: str = ""
    etag: str | None = None
    last_modified: str | None = None

    @property
    def not_modified(self) -> bool:
        return self.status_code == 304

    @property
    def is_html(self) -> bool:
        return "html" in self.content_type

    @property
    def is_pdf(self) -> bool:
        return "pdf" in self.content_type


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    title: str
    markdown: str
    words: int
    # Indicios de contenido que solo aparece con navegador (aviso, no bloqueo).
    js_hints: tuple[str, ...] = ()
    looks_like_filler: bool = False  # lorem ipsum


@dataclass(frozen=True, slots=True)
class DiscoveredUrl:
    url: str
    section: str  # grupo del sitemap ("wp-sitemap-posts-page-1.xml") o "links"


@dataclass(frozen=True, slots=True)
class Discovery:
    urls: tuple[DiscoveredUrl, ...]
    # Páginas por sección, ANTES de exclusiones y tope: para la vista previa.
    sections: dict[str, int]
    used_sitemap: bool
    truncated: bool  # había más páginas que el tope
