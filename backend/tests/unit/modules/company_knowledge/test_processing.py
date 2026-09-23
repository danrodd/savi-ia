"""Procesamiento: extracción, fragmentación, pipeline, cierre condicional y worker."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.company_knowledge.application.use_cases import (
    ProcessNextCompanyDocumentUseCase,
)
from app.modules.company_knowledge.domain.entities.processing import ExtractedText, PendingChunk
from app.modules.company_knowledge.domain.exceptions import (
    UnsupportedCompanyDocumentMediaTypeError,
)
from app.modules.company_knowledge.domain.interfaces import ProcessingOutcome
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentStatusCode,
)
from app.modules.company_knowledge.infrastructure.chunking.structural_chunker import (
    StructuralChunker,
)
from app.modules.company_knowledge.infrastructure.extraction import (
    ContentMediaTypeSniffer,
    DispatchTextExtractor,
)
from app.modules.company_knowledge.infrastructure.persistence.models import (
    CompanyDocumentChunkModel,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_document_repository import (  # noqa: E501
    SqlAlchemyDocumentRepository,
)
from app.modules.company_knowledge.infrastructure.processing import (
    CompanyDocumentWorker,
    PipelineDocumentProcessor,
)

from .conftest import HashingEmbedder, make_document, make_pdf

LONG_LINE = "Texto suficiente para superar el umbral de caracteres por pagina del extractor."


@pytest.fixture
def executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=1)


def _processor(
    executor: ThreadPoolExecutor, embedder: HashingEmbedder | None = None, **kw: int
) -> PipelineDocumentProcessor:
    return PipelineDocumentProcessor(
        extractor=DispatchTextExtractor(kw.get("max_pages", 500)),
        chunker=StructuralChunker(kw.get("chunk_tokens", 900), kw.get("overlap", 120)),
        embedder=embedder or HashingEmbedder(),
        executor=executor,
        max_chunks_per_document=kw.get("max_chunks", 2000),
    )


# ── Detección de tipo y extracción ───────────────────────────────────────


def test_pdf_renamed_as_txt_is_detected_as_pdf() -> None:
    assert ContentMediaTypeSniffer().sniff(make_pdf(["hola"]), "notas.txt") == "application/pdf"


def test_binary_with_markdown_extension_is_rejected() -> None:
    with pytest.raises(UnsupportedCompanyDocumentMediaTypeError):
        ContentMediaTypeSniffer().sniff(bytes(range(256)) * 4, "manual.md")


def test_windows_cp1252_text_is_accepted() -> None:
    content = "Política de crédito: año fiscal".encode("cp1252")
    assert ContentMediaTypeSniffer().sniff(content, "politica.txt") == "text/plain"


def test_repeated_headers_are_removed_from_pdf_pages() -> None:
    pages = [f"EMPRESA X CONFIDENCIAL\n{LONG_LINE} {i}" for i in range(4)]
    extracted = DispatchTextExtractor(500).extract(make_pdf(pages), "application/pdf")
    assert all("CONFIDENCIAL" not in page for page in extracted.pages)


# ── Fragmentación ────────────────────────────────────────────────────────


def test_markdown_chunks_keep_the_current_heading() -> None:
    text = "# Caja\n\nApertura del turno.\n\n# Devoluciones\n\nRequiere supervisor."
    chunks = StructuralChunker(3, 0).chunk(ExtractedText([text], "text/markdown"))
    assert [(c.heading, c.text) for c in chunks] == [
        ("Caja", "# Caja\nApertura del turno."),
        ("Devoluciones", "# Devoluciones\nRequiere supervisor."),
    ]
    assert chunks[1].embed_text.startswith("Devoluciones\n")


def test_every_section_name_stays_in_a_chunk_that_groups_several() -> None:
    """Precios de planes: sin el nombre de cada plan, los precios no sirven."""
    text = "### PLAN R-A\n\n$257.000/mes\n\n### PLAN R-B\n\n$411.300/mes"
    chunks = StructuralChunker(900, 0).chunk(ExtractedText([text], "text/markdown"))
    assert len(chunks) == 1
    assert "PLAN R-A\n$257.000/mes" in chunks[0].text
    assert "PLAN R-B\n$411.300/mes" in chunks[0].text


def test_headings_without_body_are_kept() -> None:
    """Cláusulas o direcciones escritas como títulos, sin párrafo debajo."""
    text = (
        "## Contrato\n\n### Hasta 15 kilos de equipaje sin sobreprecio.\n"
        "### Llegar media hora antes.\n\n## Sedes\n\nTerminal del Sur."
    )
    chunks = StructuralChunker(900, 0).chunk(ExtractedText([text], "text/markdown"))
    joined = "\n".join(c.text for c in chunks)
    assert "15 kilos de equipaje" in joined
    assert "media hora antes" in joined
    assert "## Sedes\nTerminal del Sur." in joined


def test_pdf_chunks_keep_their_page_range() -> None:
    pages = ["Primera parte del procedimiento.", "Segunda parte del procedimiento."]
    chunks = StructuralChunker(900, 0).chunk(ExtractedText(pages, "application/pdf", 2))
    assert (chunks[0].page_from, chunks[0].page_to) == (1, 2)


def test_oversized_paragraph_is_split_by_sentences() -> None:
    paragraph = " ".join(f"Oración número {i} del procedimiento." for i in range(60))
    chunks = StructuralChunker(50, 0).chunk(ExtractedText([paragraph], "text/plain"))
    assert len(chunks) > 1
    assert all(len(c.text) // 4 <= 60 for c in chunks)


# ── Pipeline ─────────────────────────────────────────────────────────────


async def test_pipeline_produces_ready_outcome_with_vectors(executor: ThreadPoolExecutor) -> None:
    outcome = await _processor(executor).process(
        b"# Caja\n\nCierre diario del turno.", "text/markdown"
    )
    assert outcome.status == DocumentStatus.READY
    assert outcome.embedding_model == "test-hashing"
    assert len(outcome.chunks[0].embedding) == 64 * 4


async def test_scanned_pdf_is_no_text(executor: ThreadPoolExecutor) -> None:
    outcome = await _processor(executor).process(make_pdf(["", "  ", ""]), "application/pdf")
    assert outcome.status == DocumentStatus.NO_TEXT
    assert outcome.chunks == []


async def test_pdf_over_page_limit_fails(executor: ThreadPoolExecutor) -> None:
    pdf = make_pdf([LONG_LINE] * 3)
    outcome = await _processor(executor, max_pages=2).process(pdf, "application/pdf")
    assert (outcome.status, outcome.status_code) == (
        DocumentStatus.FAILED,
        DocumentStatusCode.TOO_MANY_PAGES,
    )


async def test_unreadable_pdf_fails(executor: ThreadPoolExecutor) -> None:
    outcome = await _processor(executor).process(b"%PDF-1.4 basura", "application/pdf")
    assert outcome.status_code == DocumentStatusCode.PDF_UNREADABLE


async def test_too_many_chunks_fails_without_chunks(executor: ThreadPoolExecutor) -> None:
    text = "\n\n".join(f"Parrafo {i} con contenido." for i in range(20))
    outcome = await _processor(executor, chunk_tokens=5, max_chunks=3).process(
        text.encode(), "text/plain"
    )
    assert outcome.status_code == DocumentStatusCode.TOO_MANY_CHUNKS
    assert outcome.chunks == []


# ── Cierre condicional (la carrera) ──────────────────────────────────────


def _ready_outcome() -> ProcessingOutcome:
    return ProcessingOutcome(
        status=DocumentStatus.READY,
        char_count=10,
        embedding_model="test-hashing",
        chunks=[PendingChunk(ordinal=0, text="hola", embedding=b"\x00" * 256)],
    )


async def _count_chunks(sm: async_sessionmaker[AsyncSession]) -> int:
    async with sm() as session:
        return int(
            (await session.execute(select(func.count(CompanyDocumentChunkModel.id)))).scalar_one()
        )


async def test_document_deleted_while_processing_is_not_resurrected(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlAlchemyDocumentRepository(sessionmaker_)
    document = await repo.save(make_document())
    claimed = await repo.claim_next_pending()
    assert claimed is not None

    await repo.soft_delete(document.id)  # el admin lo elimina a mitad
    completed = await repo.complete_processing(document.id, claimed.version, _ready_outcome())

    assert completed is False
    stored = await repo.get_by_id(document.id)
    assert stored is not None and stored.is_deleted
    assert await _count_chunks(sessionmaker_) == 0


async def test_document_replaced_while_processing_discards_the_old_result(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlAlchemyDocumentRepository(sessionmaker_)
    document = await repo.save(make_document())
    claimed = await repo.claim_next_pending()
    assert claimed is not None

    replaced = await repo.get_by_id(document.id)
    assert replaced is not None
    replaced.version += 1
    replaced.status = DocumentStatus.PENDING
    await repo.save(replaced)

    assert await repo.complete_processing(document.id, claimed.version, _ready_outcome()) is False
    stored = await repo.get_by_id(document.id)
    assert stored is not None and stored.status == DocumentStatus.PENDING


async def test_title_edit_during_processing_does_not_overwrite_the_result(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlAlchemyDocumentRepository(sessionmaker_)
    document = await repo.save(make_document())
    claimed = await repo.claim_next_pending()
    assert claimed is not None
    stale_copy = await repo.get_by_id(document.id)  # la lee el PATCH, `processing`
    assert await repo.complete_processing(document.id, claimed.version, _ready_outcome())

    assert stale_copy is not None
    stale_copy.title = "Nuevo título"
    assert await repo.update_access_metadata(stale_copy)

    stored = await repo.get_by_id(document.id)
    assert stored is not None
    assert (stored.title, stored.status, stored.chunk_count) == (
        "Nuevo título",
        DocumentStatus.READY,
        1,
    )


async def test_failed_outcome_leaves_no_partial_chunks(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlAlchemyDocumentRepository(sessionmaker_)
    document = await repo.save(make_document())
    claimed = await repo.claim_next_pending()
    assert claimed is not None
    await repo.complete_processing(
        document.id, claimed.version, ProcessingOutcome.failed(DocumentStatusCode.INTERNAL_ERROR)
    )
    stored = await repo.get_by_id(document.id)
    assert stored is not None
    assert (stored.status, stored.chunk_count, stored.embedding_model) == (
        DocumentStatus.FAILED,
        0,
        None,
    )
    assert await _count_chunks(sessionmaker_) == 0


# ── Caso de uso y worker ─────────────────────────────────────────────────


async def test_process_use_case_marks_ready_and_enforces_installation_limit(
    sessionmaker_: async_sessionmaker[AsyncSession], executor: ThreadPoolExecutor
) -> None:
    repo = SqlAlchemyDocumentRepository(sessionmaker_)
    first = await repo.save(make_document(title="Primero"))
    await repo.save_blob(first.id, b"# Caja\n\nCierre diario.")
    use_case = ProcessNextCompanyDocumentUseCase(repo, _processor(executor), max_total_chunks=1)
    assert await use_case.execute() is True
    stored = await repo.get_by_id(first.id)
    assert stored is not None and stored.status == DocumentStatus.READY

    second = await repo.save(make_document(title="Segundo"))
    await repo.save_blob(second.id, b"# Devoluciones\n\nRequiere supervisor.")
    assert await use_case.execute() is True
    over = await repo.get_by_id(second.id)
    assert over is not None
    assert (over.status, over.status_code) == (
        DocumentStatus.FAILED,
        DocumentStatusCode.INDEX_LIMIT_REACHED,
    )
    assert await use_case.execute() is False  # sin trabajo


async def test_unavailable_embedder_returns_document_to_the_queue(
    sessionmaker_: async_sessionmaker[AsyncSession], executor: ThreadPoolExecutor
) -> None:
    repo = SqlAlchemyDocumentRepository(sessionmaker_)
    document = await repo.save(make_document())
    await repo.save_blob(document.id, b"Contenido del documento.")
    use_case = ProcessNextCompanyDocumentUseCase(
        repo, _processor(executor, HashingEmbedder(available=False)), max_total_chunks=100
    )
    from app.modules.company_knowledge.domain.exceptions import EmbedderUnavailableError

    with pytest.raises(EmbedderUnavailableError):
        await use_case.execute()
    stored = await repo.get_by_id(document.id)
    assert stored is not None and stored.status == DocumentStatus.PENDING


async def test_worker_requeues_stuck_documents_and_processes_on_notify(
    sessionmaker_: async_sessionmaker[AsyncSession], executor: ThreadPoolExecutor
) -> None:
    repo = SqlAlchemyDocumentRepository(sessionmaker_)
    stuck = make_document(title="Colgado", status=DocumentStatus.PROCESSING)
    await repo.save(stuck)
    await repo.save_blob(stuck.id, b"Quedo a mitad por un reinicio.")

    worker = CompanyDocumentWorker(
        repository=repo,
        use_case=ProcessNextCompanyDocumentUseCase(repo, _processor(executor), 100),
        embedding_model="test-hashing",
        idle_timeout_s=30,
    )
    await worker.start()
    try:
        for _ in range(100):
            stored = await repo.get_by_id(stuck.id)
            if stored is not None and stored.status == DocumentStatus.READY:
                break
            await asyncio.sleep(0.05)
        assert stored is not None and stored.status == DocumentStatus.READY

        fresh = await repo.save(make_document(title="Nuevo"))
        await repo.save_blob(fresh.id, b"Subido con el worker dormido.")
        worker.notify()  # sin notify esperaría 30 s
        for _ in range(100):
            new = await repo.get_by_id(fresh.id)
            if new is not None and new.status == DocumentStatus.READY:
                break
            await asyncio.sleep(0.05)
        assert new is not None and new.status == DocumentStatus.READY
    finally:
        await worker.stop()


async def test_unique_sha256_allows_reupload_after_delete(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlAlchemyDocumentRepository(sessionmaker_)
    original = await repo.save(make_document(sha256="a" * 64))
    await repo.soft_delete(original.id)
    again = await repo.save(make_document(sha256="a" * 64))
    assert await repo.get_by_sha256("a" * 64) == await repo.get_by_id(again.id)
    assert uuid4() != again.id
