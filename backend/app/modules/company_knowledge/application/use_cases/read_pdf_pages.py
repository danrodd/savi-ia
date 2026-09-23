"""Lectura de un PDF página por página, con IA o con `pypdf` (Fase 4).

Flujo (spec §4):

1. `pypdf` analiza cada página en el executor: texto de respaldo y métricas.
2. La política decide por página: `text` o `ai`. En la Fase 4, todo `ai` si
   la lectura está activa y hay proveedor; si no, todo `text`.
3. Las páginas ya leídas con IA en esta versión se reutilizan: reprocesar
   no vuelve a pagar y un reinicio retoma donde iba.
4. El resto se agrupa en tramos y va al proveedor en paralelo acotado, con
   reintentos. Si un tramo falla, esas páginas usan el texto de `pypdf`.
5. Cada tramo se guarda al terminar.

Nunca loguea contenido: solo ids, páginas y códigos.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import Executor
from dataclasses import dataclass

from app.modules.company_knowledge.domain.entities.company_document import CompanyDocument
from app.modules.company_knowledge.domain.entities.page_reading import (
    AiReadRecord,
    AiReadResult,
    AiReadUsage,
    PageMetrics,
    PdfAnalysis,
    ReadPage,
)
from app.modules.company_knowledge.domain.entities.processing import ExtractedText
from app.modules.company_knowledge.domain.exceptions import AiReadingError
from app.modules.company_knowledge.domain.interfaces import (
    AiReaderProvider,
    DocumentPageRepository,
    KnowledgeSettingsRepository,
    PageRoutingPolicy,
    PdfPageAnalyzer,
    PdfPageReader,
)
from app.modules.company_knowledge.domain.services import AllAiPolicy, TextOnlyPolicy
from app.modules.company_knowledge.domain.value_objects import (
    AiReadErrorCode,
    AiReadOutcome,
    PageRoute,
    ReadingMethod,
)
from app.modules.company_knowledge.infrastructure.progress import get_progress_registry

logger = logging.getLogger(__name__)

PDF_MEDIA_TYPE = "application/pdf"


@dataclass(frozen=True, slots=True)
class AiReadingLimits:
    concurrency: int = 3
    pages_per_request: int = 5
    max_request_bytes: int = 8 * 1024 * 1024
    timeout_s: float = 120.0
    retry_attempts: int = 3
    retry_base_delay_s: float = 2.0


@dataclass(frozen=True, slots=True)
class PdfReadingOutcome:
    extracted: ExtractedText
    reading_method: ReadingMethod
    ai_page_count: int
    ai_cost_usd: float | None


@dataclass(frozen=True, slots=True)
class _Segment:
    pages: list[int]
    content: bytes | None
    # Una página sola más grande que el tope no se manda.
    too_large: bool = False

    @property
    def first(self) -> int:
        return self.pages[0]

    @property
    def last(self) -> int:
        return self.pages[-1]


class ReadPdfPagesUseCase:
    def __init__(
        self,
        *,
        analyzer: PdfPageAnalyzer,
        pages: DocumentPageRepository,
        settings: KnowledgeSettingsRepository,
        readers: AiReaderProvider,
        executor: Executor,
        prompt_version: int,
        limits: AiReadingLimits | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._analyzer = analyzer
        self._pages = pages
        self._settings = settings
        self._readers = readers
        self._executor = executor
        self._prompt_version = prompt_version
        self._limits = limits or AiReadingLimits()
        self._sleep = sleep

    async def execute(self, document: CompanyDocument, content: bytes) -> PdfReadingOutcome:
        """Levanta `DocumentExtractionError` si el PDF no se puede abrir."""
        loop = asyncio.get_running_loop()
        analysis: PdfAnalysis = await loop.run_in_executor(
            self._executor, self._analyzer.analyze, content
        )
        await self._pages.delete_other_versions(document.id, document.version)

        reader = await self._reader()
        policy: PageRoutingPolicy = AllAiPolicy() if reader is not None else TextOnlyPolicy()
        metrics = {page.page_number: page for page in analysis.pages}
        routes = {page.page_number: policy.decide(page) for page in analysis.pages}

        reused = {
            page.page_number: page
            for page in await self._pages.list_pages(document.id, document.version)
            if page.method == PageRoute.AI and page.prompt_version == self._prompt_version
        }
        # Lo ya leído con IA se reutiliza aunque hoy la política diga otra
        # cosa (por ejemplo, la lectura se apagó después): ya se pagó.
        pending = [
            number
            for number, route in routes.items()
            if route == PageRoute.AI and number not in reused
        ]

        read: dict[int, ReadPage] = dict(reused)
        if reader is not None and pending:
            read.update(await self._read_with_ai(document, content, reader, pending, metrics))

        text_pages = [
            _text_page(metrics[number])
            for number, route in routes.items()
            if route == PageRoute.TEXT and number not in reused
        ]
        await self._pages.save_pages(document.id, document.version, text_pages)
        read.update({page.page_number: page for page in text_pages})

        final = [_final_text(read[number], metrics[number]) for number in sorted(metrics)]
        ai_page_count = sum(1 for number in metrics if read[number].method == PageRoute.AI)
        extracted = ExtractedText(
            pages=final, media_type=PDF_MEDIA_TYPE, page_count=analysis.page_count
        )
        used_ai = bool(reused) or any(route == PageRoute.AI for route in routes.values())
        return PdfReadingOutcome(
            extracted=extracted,
            reading_method=_reading_method(ai_page_count, analysis.page_count),
            ai_page_count=ai_page_count,
            ai_cost_usd=(
                await self._pages.ai_cost(document.id, document.version) if used_ai else None
            ),
        )

    async def _reader(self) -> PdfPageReader | None:
        settings = await self._settings.get()
        if not settings.ai_reading_enabled:
            return None
        return await self._readers.build_reader()

    async def _read_with_ai(
        self,
        document: CompanyDocument,
        content: bytes,
        reader: PdfPageReader,
        pending: list[int],
        metrics: dict[int, PageMetrics],
    ) -> dict[int, ReadPage]:
        loop = asyncio.get_running_loop()
        segments: list[_Segment] = await loop.run_in_executor(
            self._executor, self._build_segments, content, pending
        )
        progress = get_progress_registry()
        progress.start(document.id, len(pending), stage="reading")
        done = 0
        results: dict[int, ReadPage] = {}
        semaphore = asyncio.Semaphore(self._limits.concurrency)

        async def run(segment: _Segment) -> None:
            nonlocal done
            async with semaphore:
                pages = await self._read_segment(document, reader, segment, metrics)
            await self._pages.save_pages(document.id, document.version, pages)
            results.update({page.page_number: page for page in pages})
            done += len(segment.pages)
            progress.advance(document.id, done)

        await asyncio.gather(*(run(segment) for segment in segments))
        return results

    def _build_segments(self, content: bytes, pages: Sequence[int]) -> list[_Segment]:
        """Tramos de páginas consecutivas hasta el tope de páginas o de bytes."""
        sizes = self._analyzer.measure_pages(content, pages)
        limit = self._limits.max_request_bytes
        groups: list[list[int]] = []
        too_large: list[int] = []
        group: list[int] = []
        group_size = 0
        for number in pages:
            size = sizes[number]
            if size > limit:
                too_large.append(number)
                continue
            fits = (
                group
                and number == group[-1] + 1
                and len(group) < self._limits.pages_per_request
                and group_size + size <= limit
            )
            if not fits and group:
                groups.append(group)
                group, group_size = [], 0
            group.append(number)
            group_size += size
        if group:
            groups.append(group)
        contents = self._analyzer.build_segments(content, groups)
        segments = [
            _Segment(pages=pages_, content=bytes_)
            for pages_, bytes_ in zip(groups, contents, strict=True)
        ]
        segments.extend(_Segment(pages=[n], content=None, too_large=True) for n in too_large)
        return sorted(segments, key=lambda segment: segment.first)

    async def _read_segment(
        self,
        document: CompanyDocument,
        reader: PdfPageReader,
        segment: _Segment,
        metrics: dict[int, PageMetrics],
    ) -> list[ReadPage]:
        if segment.too_large or segment.content is None:
            logger.info(
                "company_docs_ai_page_too_large document=%s page=%s", document.id, segment.first
            )
            return [
                _fallback_page(metrics[n], AiReadErrorCode.PAGE_TOO_LARGE) for n in segment.pages
            ]

        result, attempts, error = await self._call_with_retries(reader, segment)
        outcome = (
            AiReadOutcome.FALLBACK
            if result is None
            else (AiReadOutcome.RETRIED if attempts > 1 else AiReadOutcome.OK)
        )
        await self._pages.record_ai_read(
            AiReadRecord(
                document_id=document.id,
                version=document.version,
                page_from=segment.first,
                page_to=segment.last,
                provider=reader.provider,
                model=reader.model,
                outcome=outcome,
                uploaded_by_login=document.uploaded_by_login,
                uploaded_by_database_id=document.uploaded_by_database_id,
                usage=result.usage if result is not None else AiReadUsage(),
            )
        )
        if result is None:
            code = error.code if error is not None else AiReadErrorCode.PROVIDER_ERROR
            logger.warning(
                "company_docs_ai_segment_fallback document=%s pages=%s-%s code=%s",
                document.id,
                segment.first,
                segment.last,
                code.value,
            )
            return [_fallback_page(metrics[n], code) for n in segment.pages]

        by_number = {page.page_number: page for page in result.pages}
        pages: list[ReadPage] = []
        for number in segment.pages:
            page = by_number.get(number)
            if page is None:
                pages.append(_fallback_page(metrics[number], AiReadErrorCode.MISSING_PAGE))
                continue
            source = metrics[number]
            pages.append(
                ReadPage(
                    page_number=number,
                    method=PageRoute.AI,
                    text=page.content,
                    pypdf_chars=source.pypdf_chars,
                    image_count=source.image_count,
                    max_image_pixels=source.max_image_pixels,
                    page_type=page.page_type,
                    legible=page.legible,
                    prompt_version=self._prompt_version,
                )
            )
        return pages

    async def _call_with_retries(
        self, reader: PdfPageReader, segment: _Segment
    ) -> tuple[AiReadResult | None, int, AiReadingError | None]:
        assert segment.content is not None
        last_error: AiReadingError | None = None
        attempts = 0
        for attempt in range(self._limits.retry_attempts):
            attempts = attempt + 1
            try:
                result = await asyncio.wait_for(
                    reader.read(segment.content, segment.first, segment.last, attempt=attempt),
                    timeout=self._limits.timeout_s,
                )
                return result, attempts, None
            except TimeoutError:
                last_error = AiReadingError(AiReadErrorCode.TIMEOUT, retryable=True)
            except AiReadingError as exc:
                last_error = exc
            except Exception:  # noqa: BLE001
                # Un adaptador que no traduce su error no puede tumbar la
                # lectura del documento: esas páginas usan el respaldo.
                logger.exception("company_docs_ai_reader_unexpected_error")
                last_error = AiReadingError(AiReadErrorCode.PROVIDER_ERROR, retryable=False)
            if not last_error.retryable or attempts >= self._limits.retry_attempts:
                break
            await self._sleep(self._limits.retry_base_delay_s * (2**attempt))
        return None, attempts, last_error


def _text_page(source: PageMetrics) -> ReadPage:
    return ReadPage(
        page_number=source.page_number,
        method=PageRoute.TEXT,
        text=source.text,
        pypdf_chars=source.pypdf_chars,
        image_count=source.image_count,
        max_image_pixels=source.max_image_pixels,
    )


def _fallback_page(source: PageMetrics, code: AiReadErrorCode) -> ReadPage:
    return ReadPage(
        page_number=source.page_number,
        method=PageRoute.TEXT,
        text=source.text,
        pypdf_chars=source.pypdf_chars,
        image_count=source.image_count,
        max_image_pixels=source.max_image_pixels,
        ai_error=code,
    )


def _final_text(page: ReadPage, source: PageMetrics) -> str:
    # Si la IA no sacó nada (página ilegible) pero `pypdf` sí tenía texto, se
    # conserva ese texto: nunca se pierde lo que la lectura de siempre daba.
    if page.method == PageRoute.AI and not page.text.strip() and source.text.strip():
        return source.text
    return page.text


def _reading_method(ai_pages: int, total: int) -> ReadingMethod:
    if ai_pages == 0:
        return ReadingMethod.TEXT
    if ai_pages == total:
        return ReadingMethod.AI
    return ReadingMethod.MIXED
