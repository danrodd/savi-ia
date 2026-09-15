# ruff: noqa: E501 — script de medición con tablas markdown largas.
"""Benchmark de importación de documentos de la empresa (RNF-03).

Uso:

    uv run python -m scripts.bench_company_ingest
    uv run python -m scripts.bench_company_ingest --chunk-tokens 900 450

Genera documentos DENSOS del tamaño de uno real (~3.000 caracteres por página,
como una hoja carta llena) y mide cada etapa con los mismos componentes y
parámetros que producción (hilos de ONNX = núcleos ÷ 2, un hilo de ingesta):

- extracción (pypdf / decodificación de texto);
- fragmentación;
- embeddings (ONNX);
- persistencia de fragmentos y carga en el índice (SQLite temporal: en
  Postgres la escritura es comparable o más rápida).

También cuenta los tokens REALES de cada fragmento con el tokenizer del
modelo: e5 trunca en 512, lo que exceda no entra en el vector.

Escribe `docs/company_knowledge/bench-importacion.md`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tokenizers import Tokenizer

from app.infrastructure.database.base import Base
from app.modules.company_knowledge.application.use_cases import (
    ProcessNextCompanyDocumentUseCase,
)
from app.modules.company_knowledge.domain.entities.company_document import CompanyDocument
from app.modules.company_knowledge.domain.value_objects.visibility import DocumentVisibility
from app.modules.company_knowledge.infrastructure.chunking.structural_chunker import (
    StructuralChunker,
)
from app.modules.company_knowledge.infrastructure.embeddings import (
    FastEmbedEmbedder,
    models_root,
)
from app.modules.company_knowledge.infrastructure.extraction import DispatchTextExtractor
from app.modules.company_knowledge.infrastructure.index import (
    InMemoryDocumentIndex,
    SearchSettings,
)
from app.modules.company_knowledge.infrastructure.persistence.models import (
    CompanyDocumentBlobModel,
    CompanyDocumentChunkModel,
    CompanyDocumentDatabaseModel,
    CompanyDocumentModel,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_document_repository import (  # noqa: E501
    SqlAlchemyDocumentRepository,
)
from app.modules.company_knowledge.infrastructure.processing import PipelineDocumentProcessor
from app.modules.conversations.infrastructure.persistence.models import (
    ConversationModel,
    MessageModel,
)
from app.modules.erp_databases.infrastructure.persistence import ErpDatabaseModel
from scripts.build_eval_pdfs import build_pdf

ROOT = Path(__file__).resolve().parents[1]
EVAL_DOCS = ROOT / "tests" / "fixtures" / "company_knowledge" / "eval" / "documents"
REPORT = ROOT / "docs" / "company_knowledge" / "bench-importacion.md"
MODEL = "intfloat/multilingual-e5-small"
CHARS_PER_PAGE = 3000
MODEL_MAX_TOKENS = 512


@dataclass
class Case:
    name: str
    media_type: str
    content: bytes
    pages: int | None


def _sentences() -> list[str]:
    """Oraciones reales del set sintético, para que el texto no sea basura."""
    text = " ".join(
        p.read_text(encoding="utf-8") for p in EVAL_DOCS.iterdir() if p.suffix in {".md", ".txt"}
    )
    parts = [s.strip() for s in text.replace("\n", " ").split(". ") if len(s.strip()) > 30]
    return [s.rstrip(".") + "." for s in parts]


def _page_text(rng: random.Random, sentences: list[str], number: int) -> str:
    paragraphs: list[str] = [f"Sección {number}. Procedimiento operativo {rng.randint(1, 99)}"]
    size = len(paragraphs[0])
    while size < CHARS_PER_PAGE:
        paragraph = " ".join(rng.sample(sentences, 4))
        paragraphs.append(paragraph)
        size += len(paragraph)
    return "\n\n".join(paragraphs)


def _cases(pdf_pages: list[int], text_mb: list[float]) -> list[Case]:
    rng = random.Random(7)
    sentences = _sentences()
    cases: list[Case] = []
    for pages in pdf_pages:
        body = [_page_text(rng, sentences, i + 1) for i in range(pages)]
        cases.append(Case(f"PDF {pages} páginas", "application/pdf", build_pdf(body), pages))
    for mb in text_mb:
        chunks: list[str] = []
        size, number = 0, 1
        while size < mb * 1024 * 1024:
            part = f"## Sección {number}\n\n" + _page_text(rng, sentences, number)
            chunks.append(part)
            size += len(part.encode("utf-8"))
            number += 1
        content = "\n\n".join(chunks).encode("utf-8")
        cases.append(Case(f"Markdown {mb:g} MB", "text/markdown", content, None))
    return cases


def _tokenizer() -> Tokenizer:
    path = next(
        (models_root("") / "models--intfloat--multilingual-e5-small").rglob("tokenizer.json")
    )
    tokenizer = Tokenizer.from_file(str(path))
    tokenizer.no_truncation()
    return tokenizer


async def _end_to_end(
    case: Case, embedder: FastEmbedEmbedder, chunk_tokens: int, overlap: int
) -> dict[str, Any]:
    """Camino completo del worker: claim → procesar → guardar → índice."""
    tmp = Path(tempfile.mkdtemp())
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp / 'bench.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                ErpDatabaseModel.__table__,
                ConversationModel.__table__,
                MessageModel.__table__,
                CompanyDocumentModel.__table__,
                CompanyDocumentDatabaseModel.__table__,
                CompanyDocumentBlobModel.__table__,
                CompanyDocumentChunkModel.__table__,
            ],
        )
    repo = SqlAlchemyDocumentRepository(async_sessionmaker(bind=engine, expire_on_commit=False))
    executor = ThreadPoolExecutor(max_workers=1)
    processor = PipelineDocumentProcessor(
        extractor=DispatchTextExtractor(500),
        chunker=StructuralChunker(chunk_tokens, overlap),
        embedder=embedder,
        executor=executor,
        max_chunks_per_document=2000,
    )
    index = InMemoryDocumentIndex(
        repository=repo,
        embedder=embedder,
        build_executor=executor,
        search_executor=ThreadPoolExecutor(max_workers=2),
        settings=SearchSettings(),
    )
    await index.load()
    use_case = ProcessNextCompanyDocumentUseCase(repo, processor, 50_000, index)
    document = CompanyDocument(
        title=case.name,
        original_filename=case.name,
        media_type=case.media_type,
        size_bytes=len(case.content),
        sha256=uuid4().hex,
        visibility=DocumentVisibility.ALL,
        uploaded_by_login="BENCH",
        uploaded_by_database_id=uuid4(),
        uploaded_by_user_id=1,
    )
    await repo.save(document)
    await repo.save_blob(document.id, case.content)
    started = time.perf_counter()
    await use_case.execute()
    total = time.perf_counter() - started
    saved = await repo.get_by_id(document.id)
    await engine.dispose()
    executor.shutdown(wait=False)
    return {"total_s": total, "status": saved.status.value if saved else "?"}


async def _run(
    case: Case, embedder: FastEmbedEmbedder, tokenizer: Tokenizer, chunk_tokens: int, overlap: int
) -> dict[str, Any]:
    extractor = DispatchTextExtractor(500)
    chunker = StructuralChunker(chunk_tokens, overlap)

    t0 = time.perf_counter()
    extracted = extractor.extract(case.content, case.media_type)
    t1 = time.perf_counter()
    drafts = chunker.chunk(extracted)
    t2 = time.perf_counter()
    texts = [d.embed_text for d in drafts]
    for start in range(0, len(texts), 32):
        embedder.embed_passages(texts[start : start + 32])
    t3 = time.perf_counter()

    tokens = [len(tokenizer.encode(f"passage: {t}").ids) for t in texts]
    truncated = [n for n in tokens if n > MODEL_MAX_TOKENS]
    lost = sum(n - MODEL_MAX_TOKENS for n in truncated) / max(sum(tokens), 1)
    e2e = await _end_to_end(case, embedder, chunk_tokens, overlap)
    return {
        "case": case.name,
        "chunk_tokens": chunk_tokens,
        "size_kb": len(case.content) / 1024,
        "pages": extracted.page_count,
        "chars": extracted.char_count,
        "chunks": len(drafts),
        "extract_s": t1 - t0,
        "chunk_s": t2 - t1,
        "embed_s": t3 - t2,
        "end_to_end_s": e2e["total_s"],
        "status": e2e["status"],
        "tokens_median": statistics.median(tokens) if tokens else 0,
        "tokens_max": max(tokens) if tokens else 0,
        "truncated_pct": len(truncated) / max(len(tokens), 1),
        "lost_text_pct": lost,
    }


def _render(rows: list[dict[str, Any]], threads: int) -> str:
    lines = [
        "# Benchmark de importación — resultados",
        "",
        f"> Generado por `scripts/bench_company_ingest.py`. Modelo `{MODEL}`, "
        f"{os.cpu_count()} núcleos lógicos, ONNX con {threads} hilos (como producción).",
        f"> Documentos densos de ~{CHARS_PER_PAGE} caracteres por página.",
        "",
        "## Tiempos",
        "",
        "| Documento | Fragmento | Tamaño | Fragmentos | Extracción | Fragmentación | Embeddings | **Total (worker)** | Por página | Estado |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        per_page = f"{r['end_to_end_s'] / r['pages'] * 1000:.0f} ms" if r["pages"] else "—"
        lines.append(
            f"| {r['case']} | {r['chunk_tokens']} | {r['size_kb']:.0f} KB | {r['chunks']} | {r['extract_s']:.2f} s | "
            f"{r['chunk_s']:.2f} s | {r['embed_s']:.2f} s | **{r['end_to_end_s']:.1f} s** | {per_page} | {r['status']} |"
        )
    lines += [
        "",
        "## Tokens reales por fragmento (límite del modelo: 512)",
        "",
        "| Documento | Fragmento | Mediana | Máximo | Fragmentos truncados | Texto que no entra al vector |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['case']} | {r['chunk_tokens']} | {r['tokens_median']:.0f} | {r['tokens_max']} | "
            f"{r['truncated_pct'] * 100:.0f}% | {r['lost_text_pct'] * 100:.0f}% |"
        )
    return "\n".join(lines) + "\n"


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-pages", nargs="+", type=int, default=[10, 50, 200, 500])
    parser.add_argument("--text-mb", nargs="+", type=float, default=[1.0])
    parser.add_argument("--chunk-tokens", nargs="+", type=int, default=[900])
    parser.add_argument("--overlap-ratio", type=float, default=120 / 900)
    args = parser.parse_args()

    threads = max(1, (os.cpu_count() or 2) // 2)
    embedder = FastEmbedEmbedder(MODEL, models_root(""), threads)
    t0 = time.perf_counter()
    if not embedder.is_available():
        raise SystemExit("Modelo no disponible: uv run download-embedding-model")
    print(f"Carga del modelo: {time.perf_counter() - t0:.1f} s", flush=True)
    tokenizer = _tokenizer()
    cases = _cases(args.pdf_pages, args.text_mb)

    rows: list[dict[str, Any]] = []
    for chunk_tokens in args.chunk_tokens:
        overlap = round(chunk_tokens * args.overlap_ratio)
        for case in cases:
            row = await _run(case, embedder, tokenizer, chunk_tokens, overlap)
            print(
                f"{row['case']} [{chunk_tokens}]: total {row['end_to_end_s']:.1f} s "
                f"(extracción {row['extract_s']:.1f}, embeddings {row['embed_s']:.1f}) "
                f"· {row['chunks']} fragmentos · truncados {row['truncated_pct'] * 100:.0f}% · {row['status']}",
                flush=True,
            )
            rows.append(row)
    REPORT.write_text(_render(rows, threads), encoding="utf-8")
    print(f"Informe: {REPORT}")


if __name__ == "__main__":
    asyncio.run(_main())
