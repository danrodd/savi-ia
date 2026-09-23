"""Lectura de PDF por páginas con IA (Fase 4).

El lector de IA es falso; la persistencia (páginas, registro de gasto,
configuración) es SQLite real, porque reutilizar lo ya leído y retomar
después de un corte dependen de lo que quedó guardado.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.company_knowledge.application.use_cases import (
    AiReadingLimits,
    ProcessNextCompanyDocumentUseCase,
    ReadPdfPagesUseCase,
)
from app.modules.company_knowledge.domain.entities.company_document import CompanyDocument
from app.modules.company_knowledge.domain.entities.page_reading import (
    AiPageContent,
    AiReadResult,
    AiReadUsage,
    KnowledgeSettings,
)
from app.modules.company_knowledge.domain.exceptions import AiReadingError
from app.modules.company_knowledge.domain.interfaces import (
    AiReaderAvailability,
    AiReaderProvider,
    PdfPageReader,
)
from app.modules.company_knowledge.domain.value_objects import (
    AiReadErrorCode,
    AiReadOutcome,
    DocumentStatus,
    DocumentStatusCode,
    PageRoute,
    ReadingMethod,
)
from app.modules.company_knowledge.infrastructure.chunking.structural_chunker import (
    StructuralChunker,
)
from app.modules.company_knowledge.infrastructure.extraction import (
    DispatchTextExtractor,
    PypdfPageAnalyzer,
)
from app.modules.company_knowledge.infrastructure.persistence.models import (
    CompanyDocumentAiReadModel,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_document_repository import (  # noqa: E501
    SqlAlchemyDocumentRepository,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_page_repository import (  # noqa: E501
    SqlAlchemyDocumentPageRepository,
    SqlAlchemyKnowledgeSettingsRepository,
)
from app.modules.company_knowledge.infrastructure.processing import PipelineDocumentProcessor

from .conftest import HashingEmbedder, make_document, make_pdf, make_scanned_pdf

PROMPT_VERSION = 1


@dataclass
class _Call:
    first: int
    last: int
    attempt: int
    size: int


@dataclass
class FakeReader(PdfPageReader):
    """Transcribe cada página como "Página N leída por IA".

    `fail_times` falla los primeros N pedidos con `error`. `omit` son páginas
    que la respuesta no trae. `content` permite otra transcripción por página.
    """

    fail_times: int = 0
    error: AiReadingError = field(
        default_factory=lambda: AiReadingError(AiReadErrorCode.RATE_LIMITED, retryable=True)
    )
    omit: set[int] = field(default_factory=set[int])
    content: Callable[[int], str] = lambda n: (
        f"# Página {n}\n\nTexto de la página {n} leído por IA."
    )
    delay_s: float = 0.0
    calls: list[_Call] = field(default_factory=list[_Call])
    in_flight: int = 0
    max_in_flight: int = 0

    @property
    def provider(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return "gpt-test"

    async def read(
        self, segment: bytes, first_page: int, last_page: int, *, attempt: int = 0
    ) -> AiReadResult:
        self.calls.append(_Call(first_page, last_page, attempt, len(segment)))
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            if len(self.calls) <= self.fail_times:
                raise self.error
            pages = [
                AiPageContent(
                    page_number=n,
                    page_type="texto",
                    content=self.content(n),
                    legible=bool(self.content(n)),
                )
                for n in range(first_page, last_page + 1)
                if n not in self.omit
            ]
            count = last_page - first_page + 1
            return AiReadResult(
                pages=pages,
                usage=AiReadUsage(
                    input_tokens=1000 * count, output_tokens=100 * count, cost_usd=0.001 * count
                ),
            )
        finally:
            self.in_flight -= 1


class FakeReaders(AiReaderProvider):
    def __init__(self, reader: PdfPageReader | None) -> None:
        self.reader = reader

    async def availability(self) -> AiReaderAvailability:
        if self.reader is None:
            return AiReaderAvailability(available=False, reason="Sin proveedor.")
        return AiReaderAvailability(
            available=True,
            provider=self.reader.provider,
            model=self.reader.model,
            credential_kind="api_key",
            input_price=0.1,
            output_price=0.5,
        )

    async def build_reader(self) -> PdfPageReader | None:
        return self.reader


@pytest.fixture
def executor() -> Iterator[ThreadPoolExecutor]:
    pool = ThreadPoolExecutor(max_workers=1)
    yield pool
    pool.shutdown(wait=True)


class _Sleeps:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


@dataclass
class Setup:
    documents: SqlAlchemyDocumentRepository
    pages: SqlAlchemyDocumentPageRepository
    settings: SqlAlchemyKnowledgeSettingsRepository
    executor: ThreadPoolExecutor
    sleeps: _Sleeps

    def use_case(
        self, reader: PdfPageReader | None, limits: AiReadingLimits | None = None
    ) -> ReadPdfPagesUseCase:
        return ReadPdfPagesUseCase(
            analyzer=PypdfPageAnalyzer(500),
            pages=self.pages,
            settings=self.settings,
            readers=FakeReaders(reader),
            executor=self.executor,
            prompt_version=PROMPT_VERSION,
            limits=limits or AiReadingLimits(retry_base_delay_s=1.0),
            sleep=self.sleeps,
        )

    async def document(self, content: bytes) -> CompanyDocument:
        document = make_document(media_type="application/pdf")
        document.size_bytes = len(content)
        saved = await self.documents.save(document)
        await self.documents.save_blob(saved.id, content)
        return saved


@pytest.fixture
def setup(sessionmaker_: async_sessionmaker[AsyncSession], executor: ThreadPoolExecutor) -> Setup:
    return Setup(
        documents=SqlAlchemyDocumentRepository(sessionmaker_),
        pages=SqlAlchemyDocumentPageRepository(sessionmaker_),
        settings=SqlAlchemyKnowledgeSettingsRepository(sessionmaker_),
        executor=executor,
        sleeps=_Sleeps(),
    )


async def _ai_reads(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> list[CompanyDocumentAiReadModel]:
    async with sessionmaker_() as session:
        return list(
            (
                await session.scalars(
                    select(CompanyDocumentAiReadModel).order_by(
                        CompanyDocumentAiReadModel.page_from
                    )
                )
            ).all()
        )


# ── Lectura con IA ─────────────────────────────────────────────────────────


async def test_scanned_pdf_is_read_by_ai_page_by_page(
    setup: Setup, sessionmaker_: async_sessionmaker[AsyncSession]
) -> None:
    content = make_scanned_pdf(3)
    document = await setup.document(content)
    reader = FakeReader()

    outcome = await setup.use_case(reader).execute(document, content)

    assert outcome.reading_method == ReadingMethod.AI
    assert outcome.ai_page_count == 3
    assert outcome.extracted.page_count == 3
    assert outcome.extracted.pages[1].startswith("# Página 2")
    assert outcome.ai_cost_usd == pytest.approx(0.003)
    stored = await setup.pages.list_pages(document.id, document.version)
    assert [(p.page_number, p.method, p.pypdf_chars, p.image_count) for p in stored] == [
        (1, PageRoute.AI, 0, 1),
        (2, PageRoute.AI, 0, 1),
        (3, PageRoute.AI, 0, 1),
    ]
    assert all(p.prompt_version == PROMPT_VERSION for p in stored)
    reads = await _ai_reads(sessionmaker_)
    assert [(r.page_from, r.page_to, r.outcome) for r in reads] == [(1, 3, AiReadOutcome.OK.value)]
    assert reads[0].uploaded_by_login == "ADMIN"


async def test_disabled_ai_reading_keeps_the_text_layer_and_calls_nobody(setup: Setup) -> None:
    await setup.settings.save(KnowledgeSettings(ai_reading_enabled=False, updated_by_login="ADMIN"))
    content = make_pdf(["Manual de caja con texto digital suficiente para leerse bien."])
    document = await setup.document(content)
    reader = FakeReader()

    outcome = await setup.use_case(reader).execute(document, content)

    assert reader.calls == []
    assert outcome.reading_method == ReadingMethod.TEXT
    assert outcome.ai_cost_usd is None
    assert "Manual de caja" in outcome.extracted.pages[0]
    stored = await setup.pages.list_pages(document.id, document.version)
    assert [p.method for p in stored] == [PageRoute.TEXT]


async def test_without_a_provider_the_pdf_is_read_with_pypdf(setup: Setup) -> None:
    content = make_pdf(["Texto digital."])
    document = await setup.document(content)

    outcome = await setup.use_case(None).execute(document, content)

    assert outcome.reading_method == ReadingMethod.TEXT
    assert outcome.ai_page_count == 0


async def test_pages_are_grouped_in_segments_with_bounded_concurrency(setup: Setup) -> None:
    content = make_scanned_pdf(7)
    document = await setup.document(content)
    reader = FakeReader(delay_s=0.02)
    limits = AiReadingLimits(concurrency=2, pages_per_request=3)

    await setup.use_case(reader, limits).execute(document, content)

    assert sorted((c.first, c.last) for c in reader.calls) == [(1, 3), (4, 6), (7, 7)]
    assert reader.max_in_flight == 2


async def test_byte_limit_splits_segments_and_skips_oversized_pages(setup: Setup) -> None:
    content = make_scanned_pdf(3)
    document = await setup.document(content)
    one_page = PypdfPageAnalyzer(500).measure_pages(content, [1])[1]
    reader = FakeReader()

    # Una página entra; dos no.
    await setup.use_case(reader, AiReadingLimits(max_request_bytes=one_page + 100)).execute(
        document, content
    )
    assert [(c.first, c.last) for c in reader.calls] == [(1, 1), (2, 2), (3, 3)]

    # Ni una página entra: no se manda nada y se usa el respaldo.
    other = await setup.document(make_scanned_pdf(2, width=41))
    blob = await setup.documents.get_blob(other.id)
    assert blob is not None
    tiny = FakeReader()
    outcome = await setup.use_case(tiny, AiReadingLimits(max_request_bytes=100)).execute(
        other, blob
    )
    assert tiny.calls == []
    assert outcome.reading_method == ReadingMethod.TEXT
    stored = await setup.pages.list_pages(other.id, other.version)
    assert {p.ai_error for p in stored} == {AiReadErrorCode.PAGE_TOO_LARGE}


async def test_retryable_errors_back_off_and_the_prompt_knows_it_is_a_retry(
    setup: Setup, sessionmaker_: async_sessionmaker[AsyncSession]
) -> None:
    content = make_scanned_pdf(1)
    document = await setup.document(content)
    reader = FakeReader(fail_times=2)

    outcome = await setup.use_case(reader).execute(document, content)

    assert [c.attempt for c in reader.calls] == [0, 1, 2]
    assert setup.sleeps.delays == [1.0, 2.0]
    assert outcome.reading_method == ReadingMethod.AI
    reads = await _ai_reads(sessionmaker_)
    assert [r.outcome for r in reads] == [AiReadOutcome.RETRIED.value]


async def test_non_retryable_error_falls_back_to_pypdf_at_once(
    setup: Setup, sessionmaker_: async_sessionmaker[AsyncSession]
) -> None:
    content = make_pdf(["Texto digital de respaldo en la página uno."])
    document = await setup.document(content)
    reader = FakeReader(
        fail_times=99, error=AiReadingError(AiReadErrorCode.UNAVAILABLE, retryable=False)
    )

    outcome = await setup.use_case(reader).execute(document, content)

    assert len(reader.calls) == 1
    assert setup.sleeps.delays == []
    assert outcome.reading_method == ReadingMethod.TEXT
    assert "Texto digital de respaldo" in outcome.extracted.pages[0]
    stored = await setup.pages.list_pages(document.id, document.version)
    assert [(p.method, p.ai_error) for p in stored] == [
        (PageRoute.TEXT, AiReadErrorCode.UNAVAILABLE)
    ]
    reads = await _ai_reads(sessionmaker_)
    assert [(r.outcome, r.cost_usd) for r in reads] == [(AiReadOutcome.FALLBACK.value, None)]


async def test_retries_are_exhausted_then_the_segment_falls_back(setup: Setup) -> None:
    content = make_scanned_pdf(2)
    document = await setup.document(content)
    reader = FakeReader(fail_times=99)

    outcome = await setup.use_case(reader).execute(document, content)

    assert len(reader.calls) == 3
    assert outcome.reading_method == ReadingMethod.TEXT
    stored = await setup.pages.list_pages(document.id, document.version)
    assert {p.ai_error for p in stored} == {AiReadErrorCode.RATE_LIMITED}


async def test_a_slow_provider_times_out_and_falls_back(setup: Setup) -> None:
    content = make_scanned_pdf(1)
    document = await setup.document(content)
    reader = FakeReader(delay_s=1.0)
    limits = AiReadingLimits(timeout_s=0.01, retry_attempts=2)

    outcome = await setup.use_case(reader, limits).execute(document, content)

    assert len(reader.calls) == 2
    assert outcome.ai_page_count == 0
    stored = await setup.pages.list_pages(document.id, document.version)
    assert stored[0].ai_error == AiReadErrorCode.TIMEOUT


async def test_a_page_missing_from_the_answer_uses_the_text_layer(setup: Setup) -> None:
    content = make_pdf(["Uno con texto.", "Dos con texto.", "Tres con texto."])
    document = await setup.document(content)
    reader = FakeReader(omit={2})

    outcome = await setup.use_case(reader).execute(document, content)

    assert outcome.reading_method == ReadingMethod.MIXED
    assert outcome.ai_page_count == 2
    assert "Dos con texto." in outcome.extracted.pages[1]
    stored = {p.page_number: p for p in await setup.pages.list_pages(document.id, 1)}
    assert stored[2].ai_error == AiReadErrorCode.MISSING_PAGE


async def test_an_empty_ai_page_never_loses_the_text_layer(setup: Setup) -> None:
    content = make_pdf(["Texto que pypdf sí sacaba."])
    document = await setup.document(content)
    reader = FakeReader(content=lambda n: "")

    outcome = await setup.use_case(reader).execute(document, content)

    assert "Texto que pypdf sí sacaba." in outcome.extracted.pages[0]


# ── Reutilizar lo ya pagado ────────────────────────────────────────────────


async def test_reprocessing_reuses_ai_pages_and_does_not_pay_again(setup: Setup) -> None:
    content = make_scanned_pdf(2)
    document = await setup.document(content)
    first = FakeReader()
    await setup.use_case(first).execute(document, content)

    second = FakeReader()
    outcome = await setup.use_case(second).execute(document, content)

    assert second.calls == []
    assert outcome.reading_method == ReadingMethod.AI
    # El costo es el de la versión, no el de esta corrida.
    assert outcome.ai_cost_usd == pytest.approx(0.002)


async def test_ai_pages_are_reused_even_after_ai_reading_is_turned_off(setup: Setup) -> None:
    content = make_scanned_pdf(1)
    document = await setup.document(content)
    await setup.use_case(FakeReader()).execute(document, content)
    await setup.settings.save(KnowledgeSettings(ai_reading_enabled=False))

    outcome = await setup.use_case(FakeReader()).execute(document, content)

    assert outcome.reading_method == ReadingMethod.AI
    assert outcome.extracted.pages[0].startswith("# Página 1")


async def test_a_restart_resumes_with_the_pages_still_missing(setup: Setup) -> None:
    content = make_scanned_pdf(4)
    document = await setup.document(content)
    # Primera corrida: la IA solo devolvió las páginas 1 y 2.
    await setup.use_case(FakeReader(omit={3, 4})).execute(document, content)

    reader = FakeReader()
    await setup.use_case(reader).execute(document, content)

    assert [(c.first, c.last) for c in reader.calls] == [(3, 4)]


async def test_pages_from_a_replaced_version_are_discarded(setup: Setup) -> None:
    content = make_scanned_pdf(1)
    document = await setup.document(content)
    await setup.use_case(FakeReader()).execute(document, content)

    document.version = 2
    await setup.use_case(FakeReader()).execute(document, content)

    assert await setup.pages.list_pages(document.id, 1) == []
    assert len(await setup.pages.list_pages(document.id, 2)) == 1


async def test_a_new_prompt_version_reads_again(setup: Setup) -> None:
    content = make_scanned_pdf(1)
    document = await setup.document(content)
    await setup.use_case(FakeReader()).execute(document, content)

    newer = ReadPdfPagesUseCase(
        analyzer=PypdfPageAnalyzer(500),
        pages=setup.pages,
        settings=setup.settings,
        readers=FakeReaders(reader := FakeReader()),
        executor=setup.executor,
        prompt_version=PROMPT_VERSION + 1,
    )
    await newer.execute(document, content)

    assert len(reader.calls) == 1


# ── Integración con el worker ──────────────────────────────────────────────


def _worker(setup: Setup, reader: PdfPageReader | None) -> ProcessNextCompanyDocumentUseCase:
    processor = PipelineDocumentProcessor(
        extractor=DispatchTextExtractor(500),
        chunker=StructuralChunker(900, 120),
        embedder=HashingEmbedder(),
        executor=setup.executor,
        max_chunks_per_document=2000,
    )
    return ProcessNextCompanyDocumentUseCase(
        setup.documents, processor, 50000, None, setup.use_case(reader)
    )


async def test_a_scanned_pdf_ends_ready_and_cites_its_pages(setup: Setup) -> None:
    document = await setup.document(make_scanned_pdf(2))

    assert await _worker(setup, FakeReader()).execute()

    saved = await setup.documents.get_by_id(document.id)
    assert saved is not None
    assert (saved.status, saved.reading_method, saved.ai_page_count) == (
        DocumentStatus.READY,
        ReadingMethod.AI,
        2,
    )
    assert saved.ai_cost_usd == pytest.approx(0.002)
    chunks = await setup.documents.list_chunks(document.id)
    assert {c.page_from for c in chunks} <= {1, 2}
    assert any("leído por IA" in c.text for c in chunks)


async def test_a_scanned_pdf_without_ai_stays_no_text_like_before(setup: Setup) -> None:
    document = await setup.document(make_scanned_pdf(2))

    await _worker(setup, None).execute()

    saved = await setup.documents.get_by_id(document.id)
    assert saved is not None
    assert (saved.status, saved.status_code, saved.reading_method) == (
        DocumentStatus.NO_TEXT,
        None,
        ReadingMethod.TEXT,
    )


async def test_an_illegible_scan_is_reported_as_unreadable_by_ai(setup: Setup) -> None:
    document = await setup.document(make_scanned_pdf(1))
    reader = FakeReader(content=lambda n: "")

    await _worker(setup, reader).execute()

    saved = await setup.documents.get_by_id(document.id)
    assert saved is not None
    assert (saved.status, saved.status_code) == (
        DocumentStatus.NO_TEXT,
        DocumentStatusCode.AI_UNREADABLE,
    )


async def test_a_short_ai_page_is_not_treated_as_a_scan(setup: Setup) -> None:
    """El umbral de "parece escaneado" no aplica a lo que leyó la IA."""
    document = await setup.document(make_scanned_pdf(3))
    reader = FakeReader(content=lambda n: "Foto." if n > 1 else "Plano: 3 circuitos.")

    await _worker(setup, reader).execute()

    saved = await setup.documents.get_by_id(document.id)
    assert saved is not None
    assert saved.status == DocumentStatus.READY


async def test_markdown_documents_skip_the_page_reading(setup: Setup) -> None:
    document = make_document()
    saved = await setup.documents.save(document)
    await setup.documents.save_blob(saved.id, b"# Caja\n\nCierre diario de caja.")
    reader = FakeReader()

    await _worker(setup, reader).execute()

    result = await setup.documents.get_by_id(saved.id)
    assert result is not None
    assert (result.status, result.reading_method) == (DocumentStatus.READY, None)
    assert reader.calls == []


async def test_deleting_a_document_removes_its_pages_but_keeps_the_spend(
    setup: Setup, sessionmaker_: async_sessionmaker[AsyncSession]
) -> None:
    document = await setup.document(make_scanned_pdf(1))
    await _worker(setup, FakeReader()).execute()

    await setup.documents.soft_delete(document.id)

    assert await setup.pages.list_pages(document.id, document.version) == []
    assert len(await _ai_reads(sessionmaker_)) == 1
