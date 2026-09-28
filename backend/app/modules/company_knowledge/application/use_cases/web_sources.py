"""Fuentes web: alta, vista previa, edición, baja y refresco (Fase 5).

El rastreo vive en `crawl_web_source.py`. Una página importada es un
`CompanyDocument` con `source_kind = web`: el índice, los permisos y las
citas no distinguen su origen.
"""

import asyncio
from collections.abc import Callable, Sequence
from concurrent.futures import Executor
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.application.permissions import (
    ensure_databases_exist,
    validate_visibility,
)
from app.modules.company_knowledge.domain.entities.web_source import WebPage, WebSource
from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentConflictError,
    CompanyDocumentInvalidError,
    WebFetchError,
    WebSourceNotFoundError,
)
from app.modules.company_knowledge.domain.interfaces import (
    ContentExtractor,
    DocumentIndex,
    DocumentRepository,
    PageDiscoverer,
    WebFetcher,
    WebSourceRepository,
)
from app.modules.company_knowledge.domain.value_objects import (
    DocumentVisibility,
    RefreshFrequency,
    WebSourceMode,
    WebSourceStatus,
)
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository

_SAMPLE_CHARS = 500


def next_refresh(frequency: RefreshFrequency, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now(UTC)
    if frequency == RefreshFrequency.DAILY:
        return now + timedelta(days=1)
    if frequency == RefreshFrequency.WEEKLY:
        return now + timedelta(days=7)
    return None


# ── Vista previa ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WebSourcePreview:
    url: str  # URL final, después de redirecciones
    title: str
    sample: str
    words: int
    page_count: int
    truncated: bool
    used_sitemap: bool
    sections: dict[str, int]
    warnings: list[str] = field(default_factory=list[str])


class PreviewWebSourceUseCase:
    """Qué aprendería SAVI de esta URL, sin guardar nada."""

    def __init__(
        self,
        fetcher: WebFetcher,
        discoverer: PageDiscoverer,
        extractor: ContentExtractor,
        executor: Executor,
    ) -> None:
        self._fetcher = fetcher
        self._discoverer = discoverer
        self._extractor = extractor
        self._executor = executor

    async def execute(
        self,
        url: str,
        *,
        mode: WebSourceMode,
        max_pages: int,
        excluded_sections: Sequence[str] = (),
    ) -> WebSourcePreview:
        warnings: list[str] = []
        if not await self._fetcher.allowed_by_robots(url):
            raise CompanyDocumentInvalidError(
                "El sitio no permite que lo lean programas automáticos (robots.txt)."
            )
        result = await self._fetcher.fetch(url)
        if result.status_code in (401, 403, 429, 503):
            warnings.append(
                "El sitio respondió con un bloqueo o pidió iniciar sesión: puede que no se "
                "pueda leer."
            )
        elif result.status_code >= 400:
            raise WebFetchError(f"El sitio respondió con un error ({result.status_code}).")
        title, sample, words = "", "", 0
        if result.is_html:
            loop = asyncio.get_running_loop()
            page = await loop.run_in_executor(
                self._executor, self._extractor.extract, result.text, result.url
            )
            title, words = page.title, page.words
            sample = page.markdown[:_SAMPLE_CHARS]
            if page.js_hints:
                warnings.append(
                    "Parte del contenido parece cargarse con JavaScript "
                    f"({', '.join(page.js_hints)}); esa parte puede no leerse."
                )
            if page.looks_like_filler:
                warnings.append("La página tiene texto de relleno (lorem ipsum).")
        if mode == WebSourceMode.SITE:
            discovery = await self._discoverer.discover(
                result.url, max_pages=max_pages, excluded_sections=excluded_sections
            )
            page_count, truncated = len(discovery.urls), discovery.truncated
            sections, used_sitemap = discovery.sections, discovery.used_sitemap
            if truncated:
                warnings.append(
                    f"El sitio tiene más páginas que el tope: se leerán las primeras {max_pages}."
                )
        else:
            page_count, truncated, sections, used_sitemap = 1, False, {}, False
        return WebSourcePreview(
            url=result.url,
            title=title,
            sample=sample,
            words=words,
            page_count=page_count,
            truncated=truncated,
            used_sitemap=used_sitemap,
            sections=sections,
            warnings=warnings,
        )


# ── Alta, edición, baja y refresco ───────────────────────────────────────


class CreateWebSourceUseCase:
    def __init__(
        self,
        repository: WebSourceRepository,
        fetcher: WebFetcher,
        erp_repository: ErpDatabaseRepository,
        *,
        max_sources: int,
        max_pages_limit: int,
        notifier: Callable[[], None] | None = None,
    ) -> None:
        self._repository = repository
        self._fetcher = fetcher
        self._erp_repository = erp_repository
        self._max_sources = max_sources
        self._max_pages_limit = max_pages_limit
        self._notifier = notifier

    async def execute(
        self,
        *,
        url: str,
        mode: WebSourceMode,
        title: str | None,
        refresh: RefreshFrequency,
        max_pages: int,
        excluded_sections: Sequence[str],
        visibility: DocumentVisibility,
        modules: Sequence[ModuleCode],
        all_databases: bool,
        database_ids: Sequence[UUID],
        created_by_login: str,
        created_by_database_id: UUID,
        created_by_user_id: int,
    ) -> WebSource:
        await self._fetcher.validate(url)
        validate_visibility(visibility, modules, all_databases, database_ids)
        if not all_databases:
            await ensure_databases_exist(self._erp_repository, database_ids)
        if await self._repository.count_active() >= self._max_sources:
            raise CompanyDocumentConflictError(
                f"La instalación alcanzó el máximo de {self._max_sources} fuentes web."
            )
        source = WebSource(
            url=url.strip(),
            mode=mode,
            title=(title or "").strip() or url.strip(),
            refresh=refresh,
            max_pages=max(1, min(max_pages, self._max_pages_limit)),
            excluded_sections=list(excluded_sections),
            visibility=visibility,
            modules=list(modules),
            all_databases=all_databases,
            database_ids=list(database_ids),
            status=WebSourceStatus.PENDING,
            created_by_login=created_by_login,
            created_by_database_id=created_by_database_id,
            created_by_user_id=created_by_user_id,
        )
        await self._repository.save(source)
        if self._notifier is not None:
            self._notifier()
        return source


class UpdateWebSourceUseCase:
    """Edita la fuente y propaga los permisos a sus páginas.

    Los permisos aplican en la siguiente pregunta, como al editar un
    documento: se actualiza la vista de acceso del índice sin reprocesar.
    """

    def __init__(
        self,
        repository: WebSourceRepository,
        documents: DocumentRepository,
        erp_repository: ErpDatabaseRepository,
        *,
        max_pages_limit: int,
        index: DocumentIndex | None = None,
    ) -> None:
        self._repository = repository
        self._documents = documents
        self._erp_repository = erp_repository
        self._max_pages_limit = max_pages_limit
        self._index = index

    async def execute(
        self,
        source_id: UUID,
        *,
        title: str | None = None,
        refresh: RefreshFrequency | None = None,
        max_pages: int | None = None,
        excluded_sections: Sequence[str] | None = None,
        visibility: DocumentVisibility | None = None,
        modules: Sequence[ModuleCode] | None = None,
        all_databases: bool | None = None,
        database_ids: Sequence[UUID] | None = None,
    ) -> WebSource:
        source = await _get_active(self._repository, source_id)
        updated = replace(
            source,
            title=title.strip() if title and title.strip() else source.title,
            refresh=refresh or source.refresh,
            max_pages=(
                max(1, min(max_pages, self._max_pages_limit))
                if max_pages is not None
                else source.max_pages
            ),
            excluded_sections=(
                list(excluded_sections)
                if excluded_sections is not None
                else source.excluded_sections
            ),
            visibility=visibility or source.visibility,
            modules=list(modules) if modules is not None else source.modules,
            all_databases=all_databases if all_databases is not None else source.all_databases,
            database_ids=list(database_ids) if database_ids is not None else source.database_ids,
        )
        validate_visibility(
            updated.visibility, updated.modules, updated.all_databases, updated.database_ids
        )
        if not updated.all_databases:
            await ensure_databases_exist(self._erp_repository, updated.database_ids)
        if updated.refresh != source.refresh:
            updated.next_refresh_at = next_refresh(updated.refresh)
        await self._repository.save(updated)
        if _permissions_changed(source, updated):
            await self._propagate(updated)
        return updated

    async def _propagate(self, source: WebSource) -> None:
        for page in await self._repository.list_pages(source.id):
            document = await self._documents.get_by_id(page.document_id)
            if document is None or document.is_deleted:
                continue
            document.visibility = source.visibility
            document.modules = list(source.modules)
            document.all_databases = source.all_databases
            document.database_ids = list(source.database_ids)
            if await self._documents.update_access_metadata(document) and self._index:
                await self._index.update_metadata(document.id)


class DeleteWebSourceUseCase:
    """Baja: sus páginas salen del índice en el acto.

    Un rastreo en curso lo nota en la próxima página y se detiene.
    """

    def __init__(
        self,
        repository: WebSourceRepository,
        documents: DocumentRepository,
        index: DocumentIndex | None = None,
    ) -> None:
        self._repository = repository
        self._documents = documents
        self._index = index

    async def execute(self, source_id: UUID) -> None:
        source = await self._repository.get_by_id(source_id)
        if source is None:
            raise WebSourceNotFoundError(str(source_id))
        if source.is_deleted:
            return
        await self._repository.soft_delete(source_id)
        for page in await self._repository.list_pages(source_id):
            await remove_page(self._repository, self._documents, self._index, page)


class RefreshWebSourceUseCase:
    def __init__(
        self, repository: WebSourceRepository, notifier: Callable[[], None] | None = None
    ) -> None:
        self._repository = repository
        self._notifier = notifier

    async def execute(self, source_id: UUID) -> WebSource:
        source = await _get_active(self._repository, source_id)
        if source.status in (WebSourceStatus.CRAWLING, WebSourceStatus.PENDING):
            raise CompanyDocumentConflictError("La fuente ya se está leyendo.")
        source.status = WebSourceStatus.PENDING
        await self._repository.save(source)
        if self._notifier is not None:
            self._notifier()
        return source


# ── Consultas ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WebSourceDetail:
    source: WebSource
    pages: list[WebPage]


class ListWebSourcesUseCase:
    def __init__(self, repository: WebSourceRepository) -> None:
        self._repository = repository

    async def execute(self) -> list[WebSource]:
        return await self._repository.list_sources()


class GetWebSourceUseCase:
    def __init__(self, repository: WebSourceRepository) -> None:
        self._repository = repository

    async def execute(self, source_id: UUID) -> WebSourceDetail:
        source = await _get_active(self._repository, source_id)
        return WebSourceDetail(source, await self._repository.list_pages(source_id))


# ── Compartido ───────────────────────────────────────────────────────────


async def _get_active(repository: WebSourceRepository, source_id: UUID) -> WebSource:
    source = await repository.get_by_id(source_id)
    if source is None or source.is_deleted:
        raise WebSourceNotFoundError(str(source_id))
    return source


def _permissions_changed(before: WebSource, after: WebSource) -> bool:
    return (
        before.visibility != after.visibility
        or set(before.modules) != set(after.modules)
        or before.all_databases != after.all_databases
        or set(before.database_ids) != set(after.database_ids)
    )


async def remove_page(
    repository: WebSourceRepository,
    documents: DocumentRepository,
    index: DocumentIndex | None,
    page: WebPage,
) -> None:
    """Da de baja el documento de una página y retira la página."""
    await documents.soft_delete(page.document_id)
    if index is not None:
        await index.remove_document(page.document_id)
    await repository.delete_page(page.document_id)
