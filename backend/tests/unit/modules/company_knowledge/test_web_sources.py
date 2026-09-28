"""Fuentes web (Fase 5): repositorio, rastreo, casos de uso y worker."""

# Los HTML de prueba son datos: partirlos empeora la lectura.
# ruff: noqa: E501

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.application.use_cases import (
    CrawlWebSourceUseCase,
    CreateWebSourceUseCase,
    DeleteWebSourceUseCase,
    RefreshWebSourceUseCase,
    UpdateWebSourceUseCase,
)
from app.modules.company_knowledge.domain.entities.web_source import FetchResult, WebSource
from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentConflictError,
    UnsafeUrlError,
)
from app.modules.company_knowledge.domain.interfaces import WebFetcher
from app.modules.company_knowledge.domain.value_objects import (
    DocumentSourceKind,
    DocumentStatus,
    DocumentVisibility,
    RefreshFrequency,
    WebSourceMode,
    WebSourceStatus,
    WebSourceStatusCode,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_document_repository import (
    SqlAlchemyDocumentRepository,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_web_source_repository import (
    SqlAlchemyWebSourceRepository,
)
from app.modules.company_knowledge.infrastructure.web.content_extractor import (
    HybridContentExtractor,
)
from app.modules.company_knowledge.infrastructure.web.discovery import (
    SitemapAndLinksDiscoverer,
)
from app.modules.company_knowledge.infrastructure.web.worker import (
    WebSourceWorker,
    in_window,
    parse_window,
)

ROOT = "https://sitio.test/"
BASE = uuid4()
FOOTER = (
    "Oficina principal en la Calle 5 # 9-42, Bogotá. Teléfono de soporte 311 531 0210, "
    "comercial 315 715 2511. Escríbanos a ventas@sitio.test para cotizaciones y pedidos."
)


def _page(title: str, body: str) -> str:
    # Como un tema de Elementor: sin `<main>` ni `<footer>`, todo en `div`. El
    # menú y el pie solo se reconocen porque se repiten en cada página.
    return (
        f"<html><body><div class='menu'>Inicio Servicios Planes Contacto</div>"
        f"<div class='contenido'><h1>{title}</h1><p>{body}</p></div>"
        f"<div class='pie'>{FOOTER}</div></body></html>"
    )


def _long(text: str) -> str:
    # Más de MIN_WORDS palabras para que la página se importe.
    return f"{text} " + " ".join(f"detalle{i}" for i in range(30))


# ── Fetcher falso ────────────────────────────────────────────────────────


@dataclass
class _Response:
    status: int
    body: str = ""
    content_type: str = "text/html; charset=utf-8"
    etag: str | None = None


class FakeSite(WebFetcher):
    def __init__(self) -> None:
        self.pages: dict[str, _Response] = {}
        self.disallow: set[str] = set()
        self.requests: list[tuple[str, str | None]] = []
        self.on_fetch: dict[str, object] = {}

    def set(self, path: str, status: int, body: str = "", **kwargs: object) -> None:
        self.pages[ROOT + path] = _Response(status, body, **kwargs)  # type: ignore[arg-type]

    async def fetch(
        self, url: str, *, etag: str | None = None, last_modified: str | None = None
    ) -> FetchResult:
        self.requests.append((url, etag))
        hook = self.on_fetch.get(url)
        if callable(hook):
            await hook()  # type: ignore[misc]
        response = self.pages.get(url)
        if response is None:
            return FetchResult(url=url, status_code=404)
        if etag and response.etag == etag:
            return FetchResult(url=url, status_code=304)
        return FetchResult(
            url=url,
            status_code=response.status,
            content_type=response.content_type,
            body=response.body.encode(),
            text=response.body,
            etag=response.etag,
        )

    async def allowed_by_robots(self, url: str) -> bool:
        return url not in self.disallow

    async def validate(self, url: str) -> None:
        if "interno" in url:
            raise UnsafeUrlError("La dirección apunta a la red interna.")


def _sitemap(*paths: str) -> str:
    items = "".join(f"<url><loc>{ROOT}{p}</loc></url>" for p in paths)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'


@dataclass
class Env:
    site: FakeSite
    sources: SqlAlchemyWebSourceRepository
    documents: SqlAlchemyDocumentRepository
    crawl: CrawlWebSourceUseCase
    notified: list[int]
    removed_from_index: list[UUID]


class _IndexSpy:
    def __init__(self, removed: list[UUID]) -> None:
        self.removed = removed
        self.updated: list[UUID] = []

    async def remove_document(self, document_id: UUID) -> None:
        self.removed.append(document_id)

    async def update_metadata(self, document_id: UUID) -> None:
        self.updated.append(document_id)


@pytest.fixture
def env(sessionmaker_: async_sessionmaker[AsyncSession]) -> Env:
    site = FakeSite()
    sources = SqlAlchemyWebSourceRepository(sessionmaker_)
    documents = SqlAlchemyDocumentRepository(sessionmaker_)
    notified: list[int] = []
    removed: list[UUID] = []
    crawl = CrawlWebSourceUseCase(
        sources=sources,
        documents=documents,
        fetcher=site,
        discoverer=SitemapAndLinksDiscoverer(site, max_depth=2, request_delay_s=0),
        extractor=HybridContentExtractor(),
        executor=ThreadPoolExecutor(max_workers=1),
        request_delay_s=0,
        notifier=lambda: notified.append(1),
        index=_IndexSpy(removed),  # type: ignore[arg-type]
    )
    return Env(site, sources, documents, crawl, notified, removed)


def _source(**overrides: object) -> WebSource:
    values: dict[str, object] = {
        "url": ROOT,
        "mode": WebSourceMode.SITE,
        "title": "Sitio",
        "status": WebSourceStatus.PENDING,
        "created_by_login": "ADMIN",
        "created_by_database_id": BASE,
        "created_by_user_id": 1,
    }
    values.update(overrides)
    return WebSource(**values)  # type: ignore[arg-type]


def _standard_site(site: FakeSite) -> None:
    site.set(
        "sitemap.xml",
        200,
        _sitemap("planes", "servicios", "contacto"),
        content_type="application/xml",
    )
    site.set("", 200, _page("Inicio", _long("Somos una ferretería con 3 sedes.")), etag='"home-1"')
    site.set(
        "planes", 200, _page("Planes", _long("El plan Pro cuesta $20 al mes.")), etag='"planes-1"'
    )
    site.set("servicios", 200, _page("Servicios", _long("Cortamos madera a la medida.")))
    site.set("contacto", 200, _page("Contacto", _long("Llamanos de lunes a sábado.")))


async def _crawl(env: Env, source: WebSource | None = None) -> WebSource:
    source = source or _source()
    await env.sources.save(source)
    assert await env.crawl.execute()
    stored = await env.sources.get_by_id(source.id)
    assert stored is not None
    return stored


def _pending_again(source: WebSource) -> WebSource:
    source.status = WebSourceStatus.PENDING
    return source


# ── Rastreo ──────────────────────────────────────────────────────────────


async def test_a_site_crawl_imports_pages_as_web_documents(env: Env) -> None:
    _standard_site(env.site)

    source = await _crawl(env)

    assert source.status == WebSourceStatus.READY
    pages = {p.url: p for p in await env.sources.list_pages(source.id)}
    general = f"{ROOT}#informacion-general"
    assert set(pages) == {ROOT, f"{ROOT}planes", f"{ROOT}servicios", f"{ROOT}contacto", general}
    assert source.page_count == 5
    document = await env.documents.get_by_id(pages[f"{ROOT}planes"].document_id)
    assert document is not None
    assert (document.source_kind, document.source_url) == (DocumentSourceKind.WEB, f"{ROOT}planes")
    assert (document.status, document.media_type, document.title) == (
        DocumentStatus.PENDING,
        "text/markdown",
        "Planes",
    )
    blob = (await env.documents.get_blob(document.id) or b"").decode()
    assert "$20 al mes" in blob and f"Fuente: {ROOT}planes" in blob
    # La plantilla repetida sale de cada página y queda una vez.
    assert FOOTER not in blob
    general_blob = (await env.documents.get_blob(pages[general].document_id) or b"").decode()
    assert "311 531 0210" in general_blob
    assert env.notified == [1]


async def test_web_pages_do_not_show_up_among_uploaded_documents(env: Env) -> None:
    _standard_site(env.site)
    await _crawl(env)

    assert await env.documents.list_documents() == []
    assert len(await env.documents.list_documents(source_kind=DocumentSourceKind.WEB)) == 5


async def test_a_refresh_without_changes_creates_no_new_versions(env: Env) -> None:
    _standard_site(env.site)
    source = await _crawl(env)
    before = {p.url: p.document_id for p in await env.sources.list_pages(source.id)}
    env.notified.clear()
    env.site.requests.clear()

    source = await _crawl(env, _pending_again(source))

    for document_id in before.values():
        document = await env.documents.get_by_id(document_id)
        assert document is not None and document.version == 1
    # En modo sitio se descarga todo (la plantilla se calcula con todas las
    # páginas): el hash es lo que evita reprocesar.
    assert (f"{ROOT}planes", None) in env.site.requests
    assert env.notified == []
    assert "sin cambios" in (source.status_message or "")


async def test_page_mode_uses_conditional_requests(env: Env) -> None:
    _standard_site(env.site)
    source = await _crawl(env, _source(url=f"{ROOT}planes", mode=WebSourceMode.PAGE))
    page = (await env.sources.list_pages(source.id))[0]
    env.site.requests.clear()

    await _crawl(env, _pending_again(source))

    assert env.site.requests == [(f"{ROOT}planes", '"planes-1"')]
    document = await env.documents.get_by_id(page.document_id)
    assert document is not None and document.version == 1


async def test_a_changed_page_gets_a_new_version_and_keeps_answering(env: Env) -> None:
    _standard_site(env.site)
    source = await _crawl(env)
    page = next(p for p in await env.sources.list_pages(source.id) if p.url.endswith("planes"))
    env.site.set(
        "planes",
        200,
        _page("Planes", _long("El plan Pro ahora cuesta $25 al mes.")),
        etag='"planes-2"',
    )

    await _crawl(env, _pending_again(source))

    document = await env.documents.get_by_id(page.document_id)
    assert document is not None
    assert (document.version, document.status) == (2, DocumentStatus.PENDING)
    assert "$25 al mes" in (await env.documents.get_blob(document.id) or b"").decode()
    # No se saca del índice: la versión anterior responde hasta que la nueva esté lista.
    assert page.document_id not in env.removed_from_index


async def test_a_title_only_change_gets_a_new_version(env: Env) -> None:
    # Aparece otra página con el mismo título: la existente pasa a
    # "Contáctenos · contacto" con el texto intacto. Si solo decidiera el
    # texto, la cita quedaría con el título viejo y ambiguo.
    _standard_site(env.site)
    env.site.set("contacto", 200, _page("Contáctenos", _long("Llamanos de lunes a sábado.")))
    source = await _crawl(env)
    page = next(p for p in await env.sources.list_pages(source.id) if p.url.endswith("contacto"))
    assert page.title == "Contáctenos"
    env.site.set("servicios", 200, _page("Contáctenos", _long("Cortamos madera a la medida.")))

    await _crawl(env, _pending_again(source))

    document = await env.documents.get_by_id(page.document_id)
    assert document is not None
    assert (document.version, document.title) == (2, "Contáctenos · contacto")
    pages = {p.url: p for p in await env.sources.list_pages(source.id)}
    assert pages[f"{ROOT}contacto"].title == "Contáctenos · contacto"


async def test_a_page_that_disappears_twice_is_removed(env: Env) -> None:
    _standard_site(env.site)
    source = await _crawl(env)
    page = next(p for p in await env.sources.list_pages(source.id) if p.url.endswith("contacto"))
    env.site.set("contacto", 404)

    source = await _crawl(env, _pending_again(source))
    assert page.document_id not in env.removed_from_index  # una vez no alcanza
    source = await _crawl(env, _pending_again(source))

    assert page.document_id in env.removed_from_index
    document = await env.documents.get_by_id(page.document_id)
    assert document is not None and document.is_deleted
    assert all(not p.url.endswith("contacto") for p in await env.sources.list_pages(source.id))


async def test_a_temporary_error_keeps_the_last_good_version(env: Env) -> None:
    _standard_site(env.site)
    source = await _crawl(env)
    page = next(p for p in await env.sources.list_pages(source.id) if p.url.endswith("servicios"))
    env.site.set("servicios", 503)

    for _ in range(3):
        source = await _crawl(env, _pending_again(source))

    document = await env.documents.get_by_id(page.document_id)
    assert document is not None and not document.is_deleted
    assert page.document_id not in env.removed_from_index


async def test_robots_disallowing_the_site_fails_the_source(env: Env) -> None:
    _standard_site(env.site)
    env.site.disallow.add(ROOT)

    source = await _crawl(env)

    assert (source.status, source.status_code) == (
        WebSourceStatus.FAILED,
        WebSourceStatusCode.ROBOTS_DISALLOWED,
    )
    assert await env.sources.list_pages(source.id) == []


async def test_filler_and_duplicated_pages_are_skipped(env: Env) -> None:
    _standard_site(env.site)
    env.site.set(
        "sitemap.xml", 200, _sitemap("planes", "faqs", "copia"), content_type="application/xml"
    )
    env.site.set("faqs", 200, _page("FAQ", _long("Lorem ipsum dolor sit amet, consectetur.")))
    env.site.set("copia", 200, _page("Planes", _long("El plan Pro cuesta $20 al mes.")))

    source = await _crawl(env)

    urls = {p.url for p in await env.sources.list_pages(source.id)}
    assert f"{ROOT}faqs" not in urls
    assert f"{ROOT}copia" not in urls
    assert source.skipped_count == 2


async def test_repeated_titles_get_the_page_path(env: Env) -> None:
    _standard_site(env.site)
    env.site.set("servicios", 200, _page("Contáctenos", _long("Cortamos madera a la medida.")))
    env.site.set("contacto", 200, _page("Contáctenos", _long("Llamanos de lunes a sábado.")))

    source = await _crawl(env)

    titles = {p.url: p.title for p in await env.sources.list_pages(source.id)}
    assert titles[f"{ROOT}servicios"] == "Contáctenos · servicios"
    assert titles[f"{ROOT}contacto"] == "Contáctenos · contacto"
    assert titles[f"{ROOT}planes"] == "Planes"


async def test_page_mode_reads_only_that_url(env: Env) -> None:
    _standard_site(env.site)

    source = await _crawl(env, _source(url=f"{ROOT}planes", mode=WebSourceMode.PAGE))

    assert [p.url for p in await env.sources.list_pages(source.id)] == [f"{ROOT}planes"]


async def test_deleting_the_source_mid_crawl_stops_it(env: Env) -> None:
    _standard_site(env.site)
    source = _source()

    async def delete_now() -> None:
        await env.sources.soft_delete(source.id)

    env.site.on_fetch[f"{ROOT}servicios"] = delete_now
    await env.sources.save(source)

    assert await env.crawl.execute()

    assert await env.sources.list_pages(source.id) == []
    stored = await env.sources.get_by_id(source.id)
    assert stored is not None and stored.is_deleted


async def test_a_site_with_no_text_fails_with_a_reason(env: Env) -> None:
    env.site.set("", 200, "<html><body><div id='app'></div></body></html>")

    source = await _crawl(env, _source(mode=WebSourceMode.PAGE))

    assert (source.status, source.status_code) == (
        WebSourceStatus.FAILED,
        WebSourceStatusCode.NO_PAGES,
    )


async def test_the_crawl_does_not_overwrite_edits_made_meanwhile(env: Env) -> None:
    _standard_site(env.site)
    source = _source()

    async def edit_title() -> None:
        current = await env.sources.get_by_id(source.id)
        assert current is not None
        current.title = "Título editado durante el rastreo"
        await env.sources.save(current)

    env.site.on_fetch[f"{ROOT}planes"] = edit_title

    stored = await _crawl(env, source)

    assert stored.title == "Título editado durante el rastreo"
    assert stored.status == WebSourceStatus.READY


# ── Casos de uso ─────────────────────────────────────────────────────────


class _Erp:
    async def get_by_id(self, _database_id: UUID) -> object:
        return type("Db", (), {"is_usable": True})()


def _create(env: Env, max_sources: int = 5) -> CreateWebSourceUseCase:
    return CreateWebSourceUseCase(
        env.sources,
        env.site,
        _Erp(),  # type: ignore[arg-type]
        max_sources=max_sources,
        max_pages_limit=200,
        notifier=lambda: env.notified.append(1),
    )


async def _create_source(env: Env, url: str = ROOT, **overrides: object) -> WebSource:
    values: dict[str, object] = {
        "url": url,
        "mode": WebSourceMode.SITE,
        "title": None,
        "refresh": RefreshFrequency.WEEKLY,
        "max_pages": 500,
        "excluded_sections": [],
        "visibility": DocumentVisibility.ALL,
        "modules": [],
        "all_databases": True,
        "database_ids": [],
        "created_by_login": "ADMIN",
        "created_by_database_id": BASE,
        "created_by_user_id": 1,
    }
    values.update(overrides)
    return await _create(env).execute(**values)  # type: ignore[arg-type]


async def test_creating_a_source_queues_it_and_caps_the_pages(env: Env) -> None:
    source = await _create_source(env)

    assert (source.status, source.max_pages, source.title) == (WebSourceStatus.PENDING, 200, ROOT)
    assert env.notified == [1]


async def test_an_internal_url_cannot_be_added(env: Env) -> None:
    with pytest.raises(UnsafeUrlError):
        await _create_source(env, url="http://interno.test/admin")


async def test_the_source_limit_is_enforced(env: Env) -> None:
    await _create(env, max_sources=1).execute(
        url=ROOT,
        mode=WebSourceMode.PAGE,
        title=None,
        refresh=RefreshFrequency.MANUAL,
        max_pages=1,
        excluded_sections=[],
        visibility=DocumentVisibility.ALL,
        modules=[],
        all_databases=True,
        database_ids=[],
        created_by_login="A",
        created_by_database_id=BASE,
        created_by_user_id=1,
    )
    with pytest.raises(CompanyDocumentConflictError, match="máximo"):
        await _create(env, max_sources=1).execute(
            url=f"{ROOT}otra",
            mode=WebSourceMode.PAGE,
            title=None,
            refresh=RefreshFrequency.MANUAL,
            max_pages=1,
            excluded_sections=[],
            visibility=DocumentVisibility.ALL,
            modules=[],
            all_databases=True,
            database_ids=[],
            created_by_login="A",
            created_by_database_id=BASE,
            created_by_user_id=1,
        )


async def test_editing_permissions_reaches_every_page_in_the_next_question(env: Env) -> None:
    _standard_site(env.site)
    source = await _crawl(env)
    index = _IndexSpy([])
    use_case = UpdateWebSourceUseCase(
        env.sources,
        env.documents,
        _Erp(),
        max_pages_limit=200,
        index=index,  # type: ignore[arg-type]
    )

    await use_case.execute(
        source.id, visibility=DocumentVisibility.MODULES, modules=[ModuleCode.INVENTARIO]
    )

    pages = await env.sources.list_pages(source.id)
    for page in pages:
        document = await env.documents.get_by_id(page.document_id)
        assert document is not None
        assert (document.visibility, document.modules) == (
            DocumentVisibility.MODULES,
            [ModuleCode.INVENTARIO],
        )
    assert sorted(index.updated) == sorted(p.document_id for p in pages)


async def test_deleting_a_source_removes_its_pages_from_the_index(env: Env) -> None:
    _standard_site(env.site)
    source = await _crawl(env)
    pages = await env.sources.list_pages(source.id)
    removed: list[UUID] = []

    await DeleteWebSourceUseCase(env.sources, env.documents, _IndexSpy(removed)).execute(source.id)  # type: ignore[arg-type]

    assert sorted(removed) == sorted(p.document_id for p in pages)
    assert await env.sources.list_pages(source.id) == []
    assert await env.sources.list_sources() == []
    # Idempotente.
    await DeleteWebSourceUseCase(env.sources, env.documents).execute(source.id)


async def test_a_manual_refresh_is_rejected_while_crawling(env: Env) -> None:
    source = _source(status=WebSourceStatus.CRAWLING)
    await env.sources.save(source)

    with pytest.raises(CompanyDocumentConflictError, match="se está leyendo"):
        await RefreshWebSourceUseCase(env.sources).execute(source.id)


async def test_a_manual_refresh_queues_a_ready_source(env: Env) -> None:
    source = _source(status=WebSourceStatus.READY)
    await env.sources.save(source)
    notified: list[int] = []

    refreshed = await RefreshWebSourceUseCase(env.sources, lambda: notified.append(1)).execute(
        source.id
    )

    assert refreshed.status == WebSourceStatus.PENDING and notified == [1]


# ── Repositorio y worker ─────────────────────────────────────────────────


async def test_due_refreshes_are_queued_and_manual_ones_are_not(env: Env) -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    weekly = _source(
        status=WebSourceStatus.READY, refresh=RefreshFrequency.WEEKLY, next_refresh_at=past
    )
    manual = _source(
        status=WebSourceStatus.READY, refresh=RefreshFrequency.MANUAL, next_refresh_at=past
    )
    future = _source(
        status=WebSourceStatus.READY,
        refresh=RefreshFrequency.DAILY,
        next_refresh_at=datetime.now(UTC) + timedelta(hours=5),
    )
    for source in (weekly, manual, future):
        await env.sources.save(source)

    assert await env.sources.enqueue_due_refreshes() == 1

    statuses = {s.id: s.status for s in await env.sources.list_sources()}
    assert statuses[weekly.id] == WebSourceStatus.PENDING
    assert statuses[manual.id] == WebSourceStatus.READY
    assert statuses[future.id] == WebSourceStatus.READY


async def test_a_restart_requeues_sources_left_crawling(env: Env) -> None:
    await env.sources.save(_source(status=WebSourceStatus.CRAWLING))

    assert await env.sources.requeue_crawling() == 1
    assert (await env.sources.list_sources())[0].status == WebSourceStatus.PENDING


def test_refresh_window_parsing_and_midnight_wrap() -> None:
    assert parse_window("01:00-05:00") == (time(1, 0), time(5, 0))
    assert parse_window("basura") == (time(1, 0), time(5, 0))
    assert in_window(time(2, 30), (time(1, 0), time(5, 0)))
    assert not in_window(time(9, 0), (time(1, 0), time(5, 0)))
    assert in_window(time(23, 0), (time(22, 0), time(4, 0)))
    assert in_window(time(3, 0), (time(22, 0), time(4, 0)))


async def test_the_worker_only_queues_refreshes_inside_the_window(env: Env) -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    source = _source(status=WebSourceStatus.READY, next_refresh_at=past)
    await env.sources.save(source)

    daytime = WebSourceWorker(
        repository=env.sources,
        use_case=env.crawl,
        refresh_window="01:00-05:00",
        clock=lambda: datetime(2026, 9, 28, 14, 0),
    )
    assert not await daytime.run_once()

    night = WebSourceWorker(
        repository=env.sources,
        use_case=env.crawl,
        refresh_window="01:00-05:00",
        clock=lambda: datetime(2026, 9, 28, 2, 0),
    )
    _standard_site(env.site)
    assert await night.run_once()  # encoló el refresco y lo rastreó
