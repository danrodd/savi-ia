"""Rastreo de una fuente web: descubre, descarga, extrae y actualiza (Fase 5).

Lo corre el worker de fuentes web, una fuente a la vez:

1. Descubre las páginas (sitemap o links; en modo página, solo la URL).
2. Las descarga de a una, con pausa, pidiendo solo lo que cambió
   (`If-None-Match` / `If-Modified-Since`).
3. Extrae el contenido y, en modo sitio, quita la plantilla repetida; lo
   quitado se guarda una vez como "Información general del sitio".
4. Crea o actualiza el documento de cada página **solo si el texto cambió**
   (hash). La versión anterior sigue respondiendo hasta que la nueva está
   lista: el worker de documentos la reemplaza al terminar.
5. Una página que desaparece (404/410 o fuera del sitemap) se da de baja a
   la segunda vez seguida; un error pasajero (5xx, red) no cuenta.
6. Si el sitio entero falla, se conserva lo último bueno.
"""

import asyncio
import hashlib
import logging
from collections.abc import Callable
from concurrent.futures import Executor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from app.modules.company_knowledge.application.use_cases.web_sources import (
    next_refresh,
    remove_page,
)
from app.modules.company_knowledge.domain.entities.company_document import CompanyDocument
from app.modules.company_knowledge.domain.entities.web_source import (
    DiscoveredUrl,
    WebPage,
    WebSource,
)
from app.modules.company_knowledge.domain.exceptions import UnsafeUrlError, WebFetchError
from app.modules.company_knowledge.domain.interfaces import (
    ContentExtractor,
    DocumentIndex,
    DocumentRepository,
    PageDiscoverer,
    WebFetcher,
    WebSourceRepository,
)
from app.modules.company_knowledge.domain.value_objects import (
    DocumentSourceKind,
    DocumentStatus,
    WebPageStatus,
    WebSourceMode,
    WebSourceStatus,
    WebSourceStatusCode,
)

logger = logging.getLogger(__name__)

MIN_WORDS = 25
# Un pie con la razón social, la dirección y el teléfono ronda las 15
# palabras y es de lo más consultado: la información general no se mide con
# el mínimo de una página de contenido.
GENERAL_MIN_WORDS = 6
MISSING_LIMIT = 2
GENERAL_FRAGMENT = "#informacion-general"
GENERAL_TITLE = "Información general del sitio"
_MARKDOWN = "text/markdown"
_PDF = "application/pdf"


@dataclass
class _Fetched:
    url: str
    status: WebPageStatus = WebPageStatus.FAILED
    detail: str | None = None
    title: str = ""
    markdown: str | None = None
    footer: str = ""
    pdf: bytes | None = None
    etag: str | None = None
    last_modified: str | None = None
    gone: bool = False  # 404/410: cuenta para darla de baja


@dataclass
class _Tally:
    changed: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    removed: int = 0
    js_pages: int = 0
    warnings: list[str] = field(default_factory=list[str])


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _disambiguate_titles(fetched: list["_Fetched"]) -> None:
    """Títulos repetidos ("Contáctenos" en el contrato y en la sede) llevan su ruta.

    Muchos temas repiten el mismo encabezado en varias páginas; en una cita,
    "Contáctenos" para el contrato de transporte confunde.
    """
    counts: dict[str, int] = {}
    for item in fetched:
        if item.status == WebPageStatus.IMPORTED and item.title:
            counts[item.title] = counts.get(item.title, 0) + 1
    for item in fetched:
        if item.title and counts.get(item.title, 0) > 1:
            path = PurePosixPath(urlsplit(item.url).path).stem or urlsplit(item.url).hostname
            item.title = f"{item.title} · {path}"[:200]


def _filename(url: str, extension: str) -> str:
    parts = urlsplit(url)
    stem = PurePosixPath(parts.path).stem or parts.hostname or "pagina"
    return f"{stem[:200]}.{extension}"


class CrawlWebSourceUseCase:
    def __init__(
        self,
        *,
        sources: WebSourceRepository,
        documents: DocumentRepository,
        fetcher: WebFetcher,
        discoverer: PageDiscoverer,
        extractor: ContentExtractor,
        executor: Executor,
        request_delay_s: float,
        notifier: Callable[[], None] | None = None,
        index: DocumentIndex | None = None,
    ) -> None:
        self._sources = sources
        self._documents = documents
        self._fetcher = fetcher
        self._discoverer = discoverer
        self._extractor = extractor
        self._executor = executor
        self._delay_s = request_delay_s
        self._notifier = notifier
        self._index = index

    async def execute(self) -> bool:
        """Rastrea la próxima fuente pendiente. `False` si no había trabajo."""
        source = await self._sources.claim_next_due()
        if source is None:
            return False
        try:
            await self._crawl(source)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("company_web_crawl_failed source=%s", source.id)
            await self._finish(
                source,
                WebSourceStatus.FAILED,
                WebSourceStatusCode.INTERNAL_ERROR,
                "No se pudo leer el sitio por un error interno. Se conserva lo último leído.",
            )
        return True

    # ── Rastreo ──────────────────────────────────────────────────────────
    async def _crawl(self, source: WebSource) -> None:
        try:
            if not await self._fetcher.allowed_by_robots(source.url):
                await self._finish(
                    source,
                    WebSourceStatus.FAILED,
                    WebSourceStatusCode.ROBOTS_DISALLOWED,
                    "El sitio no permite que lo lean programas automáticos (robots.txt).",
                )
                return
            urls = await self._discover(source)
        except UnsafeUrlError as exc:
            await self._finish(
                source, WebSourceStatus.FAILED, WebSourceStatusCode.UNSAFE_URL, str(exc)
            )
            return
        except WebFetchError as exc:
            await self._finish(
                source, WebSourceStatus.FAILED, WebSourceStatusCode.UNREACHABLE, str(exc)
            )
            return

        existing = {page.url: page for page in await self._sources.list_pages(source.id)}
        tally = _Tally()
        fetched: list[_Fetched] = []
        # En modo sitio se descarga todo, sin pedido condicional: la plantilla
        # se detecta comparando TODAS las páginas, y si las que responden 304
        # quedaran afuera, el texto limpio de las demás cambiaría sin que el
        # sitio cambiara (versiones nuevas falsas). El hash evita reprocesar.
        conditional = source.mode == WebSourceMode.PAGE
        for discovered in urls:
            if await self._cancelled(source):
                logger.info("company_web_crawl_cancelled source=%s", source.id)
                return
            previous = existing.get(discovered.url) if conditional else None
            fetched.append(await self._fetch(discovered.url, previous))
            await asyncio.sleep(self._delay_s)

        await self._clean_template(source, fetched, tally)
        seen_hashes: set[str] = set()
        for item in fetched:
            await self._store(source, item, existing.get(item.url), seen_hashes, tally)
        await self._retire_missing(source, urls, fetched, existing, tally)

        if tally.changed and self._notifier is not None:
            self._notifier()
        await self._finish_with_tally(source, tally)

    async def _discover(self, source: WebSource) -> list[DiscoveredUrl]:
        if source.mode == WebSourceMode.PAGE:
            return [DiscoveredUrl(source.url, "raíz")]
        discovery = await self._discoverer.discover(
            source.url, max_pages=source.max_pages, excluded_sections=source.excluded_sections
        )
        return list(discovery.urls)

    async def _fetch(self, url: str, previous: WebPage | None) -> _Fetched:
        item = _Fetched(url=url)
        try:
            result = await self._fetcher.fetch(
                url,
                etag=previous.etag if previous else None,
                last_modified=previous.last_modified if previous else None,
            )
        except (WebFetchError, UnsafeUrlError) as exc:
            item.detail = str(exc)
            return item
        item.etag, item.last_modified = result.etag, result.last_modified
        if result.not_modified:
            item.status = WebPageStatus.UNCHANGED
        elif result.status_code in (404, 410):
            item.gone, item.detail = True, f"La página ya no existe ({result.status_code})."
        elif result.status_code >= 400:
            item.detail = f"El sitio respondió con un error ({result.status_code})."
        elif result.is_pdf:
            item.pdf, item.status = result.body, WebPageStatus.IMPORTED
            item.title = PurePosixPath(urlsplit(url).path).name or url
        elif result.is_html:
            loop = asyncio.get_running_loop()
            page = await loop.run_in_executor(
                self._executor, self._extractor.extract, result.text, result.url
            )
            item.title, item.markdown, item.footer = page.title, page.markdown, page.footer
            item.status = WebPageStatus.IMPORTED
            if page.looks_like_filler:
                item.status, item.detail = WebPageStatus.SKIPPED, "Texto de relleno (lorem ipsum)."
            elif page.js_hints:
                item.detail = (
                    f"Puede tener contenido que carga con JavaScript: {', '.join(page.js_hints)}."
                )
        else:
            item.status = WebPageStatus.SKIPPED
            item.detail = (
                f"Tipo de contenido no soportado ({result.content_type or 'desconocido'})."
            )
        return item

    async def _clean_template(
        self, source: WebSource, fetched: list[_Fetched], tally: _Tally
    ) -> None:
        tally.js_pages = sum(1 for item in fetched if item.detail and "JavaScript" in item.detail)
        if source.mode != WebSourceMode.SITE:
            return
        # El pie entra en la comparación: como se repite en todas las páginas,
        # sale del contenido de cada una y queda una vez en la información
        # general. Sin esto, en sitios con `<footer>` la dirección y el
        # teléfono se perdían (la plantilla por repetición solo lo rescataba
        # en temas armados con `div`).
        pages = {
            item.url: f"{item.markdown}\n\n{item.footer}" if item.footer else item.markdown
            for item in fetched
            if item.status == WebPageStatus.IMPORTED and item.markdown is not None
        }
        loop = asyncio.get_running_loop()
        cleaned, general = await loop.run_in_executor(
            self._executor, self._extractor.remove_boilerplate, pages
        )
        for item in fetched:
            if item.url in cleaned:
                item.markdown = cleaned[item.url]
        _disambiguate_titles(fetched)
        if len(general.split()) >= GENERAL_MIN_WORDS:
            fetched.append(
                _Fetched(
                    url=f"{source.url.split('#')[0]}{GENERAL_FRAGMENT}",
                    status=WebPageStatus.IMPORTED,
                    title=GENERAL_TITLE,
                    markdown=general,
                )
            )

    async def _store(
        self,
        source: WebSource,
        item: _Fetched,
        previous: WebPage | None,
        seen_hashes: set[str],
        tally: _Tally,
    ) -> None:
        if item.status == WebPageStatus.FAILED or item.gone:
            tally.failed += 0 if item.gone else 1
            if previous is not None and not item.gone:
                # Error pasajero: se conserva lo último bueno.
                previous.status, previous.status_detail = WebPageStatus.FAILED, item.detail
                previous.last_fetched_at = _now()
                await self._sources.save_page(previous)
            return
        if item.status == WebPageStatus.UNCHANGED:
            tally.unchanged += 1
            if previous is not None:
                previous.status, previous.missing_count = WebPageStatus.UNCHANGED, 0
                previous.last_fetched_at = _now()
                await self._sources.save_page(previous)
            return
        if item.status == WebPageStatus.SKIPPED:
            tally.skipped += 1
            return

        if item.pdf is not None:
            content, media = item.pdf, _PDF
            text_digest = digest = _hash(item.pdf)
        else:
            markdown = item.markdown or ""
            minimum = GENERAL_MIN_WORDS if item.url.endswith(GENERAL_FRAGMENT) else MIN_WORDS
            if len(markdown.split()) < minimum:
                item.status, item.detail = WebPageStatus.SKIPPED, "Sin texto útil."
                tally.skipped += 1
                return
            title = item.title or item.url
            content = f"# {title}\n\nFuente: {item.url}\n\n{markdown}".encode()
            media = _MARKDOWN
            # Dos hashes: el del texto detecta páginas repetidas con otra URL;
            # el del contenido completo (título incluido) decide la versión,
            # para que un título nuevo o desambiguado llegue a las citas.
            text_digest, digest = _hash(markdown.encode()), _hash(content)
        if text_digest in seen_hashes:
            item.status, item.detail = WebPageStatus.SKIPPED, "Igual a otra página del sitio."
            tally.skipped += 1
            return
        seen_hashes.add(text_digest)

        document = (
            await self._documents.get_by_id(previous.document_id) if previous is not None else None
        )
        if previous is not None and document is not None and not document.is_deleted:
            if previous.content_hash == digest:
                item.status = WebPageStatus.UNCHANGED
                tally.unchanged += 1
                previous.status, previous.missing_count = WebPageStatus.UNCHANGED, 0
                previous.etag, previous.last_modified = item.etag, item.last_modified
                previous.last_fetched_at = _now()
                await self._sources.save_page(previous)
                return
            await self._update_document(source, document, item, content, media)
        else:
            if previous is not None:
                # Su documento se borró por fuera: la fila vieja de la página
                # chocaría con la nueva (misma fuente y URL).
                await self._sources.delete_page(previous.document_id)
            document = await self._create_document(source, item, content, media)
        tally.changed += 1
        now = _now()
        await self._sources.save_page(
            WebPage(
                document_id=document.id,
                source_id=source.id,
                url=item.url,
                title=item.title,
                status=WebPageStatus.IMPORTED,
                status_detail=item.detail,
                etag=item.etag,
                last_modified=item.last_modified,
                content_hash=digest,
                missing_count=0,
                last_fetched_at=now,
                last_changed_at=now,
            )
        )

    async def _create_document(
        self, source: WebSource, item: _Fetched, content: bytes, media: str
    ) -> CompanyDocument:
        document = CompanyDocument(
            title=(item.title or item.url)[:200],
            original_filename=_filename(item.url, "pdf" if media == _PDF else "md"),
            media_type=media,
            size_bytes=len(content),
            # Estable por fuente y URL: dos sitios con el mismo texto no chocan
            # con el control de duplicados de la subida manual.
            sha256=_hash(f"web|{source.id}|{item.url}".encode()),
            status=DocumentStatus.PENDING,
            visibility=source.visibility,
            modules=list(source.modules),
            all_databases=source.all_databases,
            database_ids=list(source.database_ids),
            uploaded_by_login=source.created_by_login,
            uploaded_by_database_id=source.created_by_database_id,
            uploaded_by_user_id=source.created_by_user_id,
            source_kind=DocumentSourceKind.WEB,
            source_url=item.url.split("#")[0],
        )
        await self._documents.save(document)
        await self._documents.save_blob(document.id, content)
        return document

    async def _update_document(
        self,
        source: WebSource,
        document: CompanyDocument,
        item: _Fetched,
        content: bytes,
        media: str,
    ) -> None:
        # Versión nueva sin borrar fragmentos ni sacarla del índice: la
        # anterior sigue respondiendo hasta que el worker termine la nueva.
        document.version += 1
        document.title = (item.title or item.url)[:200]
        document.media_type = media
        document.size_bytes = len(content)
        document.status = DocumentStatus.PENDING
        document.status_code = None
        document.visibility = source.visibility
        document.modules = list(source.modules)
        document.all_databases = source.all_databases
        document.database_ids = list(source.database_ids)
        await self._documents.save_blob(document.id, content)
        await self._documents.save(document)

    async def _retire_missing(
        self,
        source: WebSource,
        urls: list[DiscoveredUrl],
        fetched: list[_Fetched],
        existing: dict[str, WebPage],
        tally: _Tally,
    ) -> None:
        present = {item.url for item in fetched if not item.gone}
        gone = {item.url for item in fetched if item.gone}
        discovered = {entry.url for entry in urls}
        for url, page in existing.items():
            missing = url in gone or (
                source.mode == WebSourceMode.SITE and url not in present and url not in discovered
            )
            if not missing:
                continue
            page.missing_count += 1
            if page.missing_count >= MISSING_LIMIT:
                await remove_page(self._sources, self._documents, self._index, page)
                tally.removed += 1
            else:
                # Visible como problema: si vuelve en la próxima lectura, se
                # recupera sola; si no, se da de baja.
                page.status = WebPageStatus.FAILED
                page.status_detail = (
                    "La página respondió que ya no existe"
                    if url in gone
                    else "La página ya no aparece en el sitio"
                ) + "; si sigue así en la próxima lectura, se da de baja."
                await self._sources.save_page(page)

    # ── Cierre ───────────────────────────────────────────────────────────
    async def _cancelled(self, source: WebSource) -> bool:
        current = await self._sources.get_by_id(source.id)
        return current is None or current.is_deleted

    async def _finish_with_tally(self, source: WebSource, tally: _Tally) -> None:
        active = len(await self._sources.list_pages(source.id))
        parts = [f"{active} páginas"]
        if tally.changed:
            parts.append(f"{tally.changed} nuevas o cambiadas")
        if tally.unchanged:
            parts.append(f"{tally.unchanged} sin cambios")
        if tally.skipped:
            parts.append(f"{tally.skipped} descartadas")
        if tally.failed:
            parts.append(f"{tally.failed} con error")
        if tally.removed:
            parts.append(f"{tally.removed} dadas de baja")
        message = ", ".join(parts) + "."
        if tally.js_pages:
            message += f" {tally.js_pages} páginas pueden tener contenido que carga con JavaScript."
        if active == 0:
            code = (
                WebSourceStatusCode.UNREACHABLE
                if tally.failed and not tally.skipped
                else WebSourceStatusCode.NO_PAGES
            )
            await self._finish(
                source,
                WebSourceStatus.FAILED,
                code,
                "No se encontró texto útil en el sitio. " + message,
                skipped=tally.skipped,
            )
            return
        await self._finish(
            source,
            WebSourceStatus.READY,
            None,
            message,
            page_count=active,
            skipped=tally.skipped,
        )

    async def _finish(
        self,
        source: WebSource,
        status: WebSourceStatus,
        code: WebSourceStatusCode | None,
        message: str,
        *,
        page_count: int | None = None,
        skipped: int = 0,
    ) -> None:
        # Se relee: el administrador pudo editar la fuente durante el
        # rastreo, y guardar la copia vieja pisaría sus cambios.
        current = await self._sources.get_by_id(source.id)
        if current is None or current.is_deleted:
            return
        current.status = status
        current.status_code = code
        current.status_message = message
        if page_count is not None:
            current.page_count = page_count
        current.skipped_count = skipped
        current.last_crawl_finished_at = _now()
        current.next_refresh_at = next_refresh(current.refresh)
        await self._sources.save(current)
