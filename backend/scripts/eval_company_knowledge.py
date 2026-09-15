# ruff: noqa: E501, E731 — script de evaluación: tablas markdown largas y filtros inline.
"""Spike: elección del modelo de embeddings, tamaño de fragmento y umbral.

Uso:

    uv run python -m scripts.eval_company_knowledge            # candidatos por defecto
    uv run python -m scripts.eval_company_knowledge --models intfloat/multilingual-e5-large

Corre el pipeline REAL (SQLite temporal + worker de procesamiento + índice
híbrido) sobre el set sintético de `tests/fixtures/company_knowledge/eval/`,
y mide para cada modelo y tamaño de fragmento:

- recall@6 y MRR@6 en modo vectorial, léxico (BM25) e híbrido (RRF);
- estrategias de filtrado: cuántas preguntas respondibles conservan su
  fragmento correcto y cuántas sin respuesta quedan vacías;
- indexación por página, p95 de consulta, memoria del índice y tamaño del modelo.

Escribe el informe en `docs/company_knowledge/spike-modelo-resultados.md` y los datos
crudos en `spike-modelo-resultados.json` (misma carpeta).

Nota: usa atributos internos del índice (`_snapshot`, `_vector_candidates`)
para aislar los modos vectorial y léxico. Es un script de evaluación, no
código de producción.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.company_knowledge.application.use_cases import (
    ProcessNextCompanyDocumentUseCase,
)
from app.modules.company_knowledge.domain.entities.company_document import CompanyDocument
from app.modules.company_knowledge.domain.interfaces import Embedder
from app.modules.company_knowledge.domain.services import DocumentAccessContext
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentVisibility,
)
from app.modules.company_knowledge.infrastructure.chunking.structural_chunker import (
    StructuralChunker,
)
from app.modules.company_knowledge.infrastructure.embeddings import (
    FastEmbedEmbedder,
    download_embedding_model,
    models_root,
)
from app.modules.company_knowledge.infrastructure.extraction import (
    ContentMediaTypeSniffer,
    DispatchTextExtractor,
)
from app.modules.company_knowledge.infrastructure.index import (
    InMemoryDocumentIndex,
    SearchSettings,
)
from app.modules.company_knowledge.infrastructure.index.in_memory_index import (
    _bm25_candidates,  # pyright: ignore[reportPrivateUsage]
)
from app.modules.company_knowledge.infrastructure.index.tokenizer import tokenize
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
from scripts.gemini_embedder import GeminiEmbedder, resolve_gemini_key

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "tests" / "fixtures" / "company_knowledge" / "eval"
REPORT = ROOT / "docs" / "company_knowledge" / "spike-modelo-resultados.md"
TOP_K = 6

DEFAULT_MODELS = [
    "intfloat/multilingual-e5-small",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "jinaai/jina-embeddings-v2-base-es",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
]
DEFAULT_CHUNK_TOKENS = [900, 300]
ADMIN = DocumentAccessContext(uuid4(), frozenset(), True, False)


@dataclass
class Hit:
    document: str
    page_from: int | None
    page_to: int | None
    vector: float
    bm25: float


@dataclass
class QuestionRun:
    id: str
    kind: str
    expected: list[dict[str, Any]]
    vector: list[Hit] = field(default_factory=list[Hit])
    bm25: list[Hit] = field(default_factory=list[Hit])
    hybrid: list[Hit] = field(default_factory=list[Hit])


def _matches(hit: Hit, expected: list[dict[str, Any]]) -> bool:
    for item in expected:
        if hit.document != item["document"]:
            continue
        pages = item.get("pages")
        if not pages or hit.page_from is None:
            return True
        start, end = hit.page_from, hit.page_to or hit.page_from
        if any(start <= page <= end for page in pages):
            return True
    return False


def _rank_of_first_match(hits: list[Hit], expected: list[dict[str, Any]]) -> int | None:
    for rank, hit in enumerate(hits[:TOP_K], start=1):
        if _matches(hit, expected):
            return rank
    return None


def _recall_mrr(runs: list[QuestionRun], mode: str) -> tuple[float, float]:
    answerable = [r for r in runs if r.expected]
    ranks = [_rank_of_first_match(getattr(r, mode), r.expected) for r in answerable]
    recall = sum(1 for rank in ranks if rank is not None) / len(answerable)
    mrr = sum(1 / rank for rank in ranks if rank is not None) / len(answerable)
    return recall, mrr


def _filter(hits: list[Hit], keep: Any) -> list[Hit]:
    return [hit for hit in hits if keep(hit)]


def _strategy_scores(runs: list[QuestionRun], keep: Any) -> tuple[float, float]:
    """(recall@6 respondibles tras filtrar, % sin respuesta que quedan vacías)."""
    answerable = [r for r in runs if r.expected]
    unanswerable = [r for r in runs if not r.expected]
    kept = sum(1 for r in answerable if _rank_of_first_match(_filter(r.hybrid, keep), r.expected))
    empty = sum(1 for r in unanswerable if not _filter(r.hybrid, keep))
    return kept / len(answerable), (empty / len(unanswerable)) if unanswerable else 0.0


def _threshold_study(runs: list[QuestionRun]) -> dict[str, Any]:
    # Rango completo: cada modelo tiene su propia escala de coseno
    # (e5 comprime todo en 0.75-0.90; los paraphrase/jina usan 0.0-0.6).
    single: list[dict[str, Any]] = []
    for step in range(0, 96):
        t = step / 100
        recall, rejection = _strategy_scores(runs, lambda h, t=t: h.vector >= t or h.bm25 > 0)
        single.append({"t": t, "recall": recall, "rejection": rejection})
    vector_only: list[dict[str, Any]] = []
    for step in range(0, 96):
        t = step / 100
        recall, rejection = _strategy_scores(runs, lambda h, t=t: h.vector >= t)
        vector_only.append({"t": t, "recall": recall, "rejection": rejection})
    dual: list[dict[str, Any]] = []
    for low in range(0, 95):
        for high in range(low + 1, 96):
            for bm25_min in (0.0, 1.0, 2.0, 3.0):
                t_low, t_high = low / 100, high / 100
                keep = lambda h, a=t_low, b=t_high, m=bm25_min: (
                    (h.bm25 > m and h.vector >= a) or h.vector >= b
                )
                recall, rejection = _strategy_scores(runs, keep)
                dual.append(
                    {
                        "t_low": t_low,
                        "t_high": t_high,
                        "bm25_min": bm25_min,
                        "recall": recall,
                        "rejection": rejection,
                    }
                )
    return {"production_rule": single, "vector_only": vector_only, "dual": dual}


def _best(rows: list[dict[str, Any]]) -> dict[str, Any]:
    # Prioridad: no perder respuestas; a igual recall, rechazar más; a igualdad,
    # el umbral MÁS BAJO (el más conservador frente a preguntas no vistas).
    def key(r: dict[str, Any]) -> tuple[float, float, float]:
        return (round(r["recall"], 3), round(r["rejection"], 3), -r.get("t", r.get("t_high", 0.0)))

    return max(rows, key=key)


def _model_disk_bytes(model: str) -> int:
    # Los modelos nativos se descargan desde repos espejo (p. ej. `qdrant/...-onnx-Q`):
    # se busca la carpeta por el nombre corto del modelo.
    short = model.split("/")[-1].lower()
    total = 0
    for folder in models_root("").glob("models--*"):
        if short in folder.name.lower():
            total += sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
    return total


_FILLER_SUBJECTS = [
    "El área de mercadeo",
    "La coordinación de proyectos",
    "El equipo de infraestructura",
    "La oficina de comunicaciones",
    "El comité de responsabilidad social",
    "La dirección de planeación",
]
_FILLER_ACTIONS = [
    "revisa trimestralmente el plan de actividades institucionales",
    "publica un boletín con las novedades de la organización",
    "organiza jornadas de integración con la comunidad del barrio",
    "evalúa las propuestas de mejora de los espacios físicos",
    "actualiza el archivo histórico de campañas publicitarias",
    "coordina las visitas de estudiantes en práctica",
    "documenta las lecciones aprendidas de cada proyecto",
    "mantiene el inventario de material promocional impreso",
]
_FILLER_CLOSINGS = [
    "según el cronograma aprobado al inicio del año",
    "con apoyo de los líderes de cada dependencia",
    "y deja constancia en el repositorio compartido",
    "priorizando las iniciativas de mayor impacto",
]


def _filler(rng: random.Random, chars: int) -> str:
    """Texto corporativo plausible SIN ninguno de los datos del set de preguntas."""
    paragraphs: list[str] = []
    size = 0
    while size < chars:
        sentences = [
            f"{rng.choice(_FILLER_SUBJECTS)} {rng.choice(_FILLER_ACTIONS)} {rng.choice(_FILLER_CLOSINGS)}."
            for _ in range(4)
        ]
        paragraph = " ".join(sentences)
        paragraphs.append(paragraph)
        size += len(paragraph)
    return "\n\n".join(paragraphs)


def _lengthen(text: str, name: str) -> str:
    """Documento largo: cada párrafo original separado por 1.000-4.000 caracteres
    de relleno, para que las respuestas caigan en posiciones variadas del
    fragmento (incluida la cola que e5 trunca a 512 tokens)."""
    rng = random.Random(name)
    parts = [p for p in text.split("\n\n") if p.strip()]
    out = [_filler(rng, 6000)]
    for part in parts:
        out.append(part)
        out.append(_filler(rng, rng.randint(1000, 4000)))
    return "\n\n".join(out)


async def _evaluate(
    model: str,
    chunk_tokens: int,
    questions: list[dict[str, Any]],
    long_docs: bool = False,
    gemini_key: str | None = None,
) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp())
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp / 'eval.db').as_posix()}")
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
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    repo = SqlAlchemyDocumentRepository(sessionmaker)
    # `gemini/<modelo>` = embeddings en la nube (spike); el resto, ONNX local.
    embedder: Embedder = (
        GeminiEmbedder(model.removeprefix("gemini/"), gemini_key or "")
        if model.startswith("gemini/")
        else FastEmbedEmbedder(model, models_root(""), 4)
    )
    if not embedder.is_available():
        raise SystemExit(f"No se pudo cargar {model}. Probá con --download.")
    executor = ThreadPoolExecutor(max_workers=1)
    processor = PipelineDocumentProcessor(
        extractor=DispatchTextExtractor(500),
        chunker=StructuralChunker(chunk_tokens, max(0, chunk_tokens // 8)),
        embedder=embedder,
        executor=executor,
        max_chunks_per_document=5000,
    )
    process = ProcessNextCompanyDocumentUseCase(repo, processor, max_total_chunks=1_000_000)
    sniffer = ContentMediaTypeSniffer()

    pages = 0
    for path in sorted((EVAL_DIR / "documents").iterdir()):
        if long_docs and path.suffix == ".pdf":
            continue
        content = (
            _lengthen(path.read_text(encoding="utf-8"), path.name).encode()
            if long_docs
            else path.read_bytes()
        )
        document = CompanyDocument(
            title=path.name,
            original_filename=path.name,
            media_type=sniffer.sniff(content, path.name),
            size_bytes=len(content),
            sha256=uuid4().hex,
            visibility=DocumentVisibility.ALL,
            uploaded_by_login="EVAL",
            uploaded_by_database_id=uuid4(),
            uploaded_by_user_id=1,
        )
        await repo.save(document)
        await repo.save_blob(document.id, content)

    started = time.perf_counter()
    while await process.execute():
        pass
    index_seconds = time.perf_counter() - started
    docs = await repo.list_documents(limit=1000)
    failed = [d.title for d in docs if d.status != DocumentStatus.READY]
    pages = sum(d.page_count or 1 for d in docs)

    index = InMemoryDocumentIndex(
        repository=repo,
        embedder=embedder,
        build_executor=executor,
        search_executor=ThreadPoolExecutor(max_workers=2),
        settings=SearchSettings(
            candidates=50,
            limit=TOP_K,
            max_per_document=3,
            max_context_chars=10**9,
            min_similarity=0.0,
        ),
    )
    await index.load()
    snapshot = index._snapshot  # pyright: ignore[reportPrivateUsage]
    allowed = list(range(len(snapshot.docs)))

    def hit_for_row(row: int, vector: float, bm25: float) -> Hit:
        doc_index = int(snapshot.row_doc[row])
        doc = snapshot.docs[doc_index]
        chunk = doc.chunks[row - snapshot.offsets[doc_index]]
        return Hit(doc.view.title, chunk.page_from, chunk.page_to, vector, bm25)

    runs: list[QuestionRun] = []
    latencies: list[float] = []
    for q in questions:
        vector_scores = index._vector_candidates(snapshot, allowed, q["question"])  # pyright: ignore[reportPrivateUsage]
        bm25_scores = _bm25_candidates(snapshot, allowed, tokenize(q["question"]), 50)
        run = QuestionRun(q["id"], q["kind"], q["expected"])
        run.vector = [
            hit_for_row(row, score, bm25_scores.get(row, 0.0))
            for row, score in sorted(vector_scores.items(), key=lambda x: x[1], reverse=True)[
                :TOP_K
            ]
        ]
        run.bm25 = [
            hit_for_row(row, vector_scores.get(row, 0.0), score)
            for row, score in sorted(bm25_scores.items(), key=lambda x: x[1], reverse=True)[:TOP_K]
        ]
        t0 = time.perf_counter()
        hybrid = await index.search(q["question"], ADMIN, limit=TOP_K)
        latencies.append((time.perf_counter() - t0) * 1000)
        run.hybrid = [
            Hit(h.title, h.page_from, h.page_to, h.vector_score, h.bm25_score) for h in hybrid
        ]
        runs.append(run)

    await engine.dispose()
    executor.shutdown(wait=False)
    metrics = {mode: _recall_mrr(runs, mode) for mode in ("vector", "bm25", "hybrid")}
    study = _threshold_study(runs)
    return {
        "model": model,
        "chunk_tokens": chunk_tokens,
        "chunks": snapshot.total_chunks,
        "failed_documents": failed,
        "index_ms_per_page": round(index_seconds * 1000 / max(pages, 1), 1),
        "query_p95_ms": round(statistics.quantiles(latencies, n=20)[18], 1),
        "index_memory_bytes": index.status().memory_bytes,
        "model_disk_bytes": _model_disk_bytes(model),
        "cloud_usage": (
            {
                "requests": embedder.usage.requests,
                "texts": embedder.usage.texts,
                "retries_429": embedder.usage.retries_429,
                "waited_for_quota_s": round(embedder.usage.waited_s, 1),
                "api_s": round(embedder.usage.api_s, 2),
                "query_embed_ms_median": round(statistics.median(embedder.usage.query_ms), 0)
                if embedder.usage.query_ms
                else None,
            }
            if isinstance(embedder, GeminiEmbedder)
            else None
        ),
        "metrics": {
            mode: {"recall": round(r, 3), "mrr": round(m, 3)} for mode, (r, m) in metrics.items()
        },
        # Con 8 documentos, recall@6 discrimina poco: recall@1 y @3 del híbrido sí.
        "hybrid_recall_at": {
            str(k): round(
                sum(
                    1
                    for r in runs
                    if r.expected
                    and (rank := _rank_of_first_match(r.hybrid, r.expected))
                    and rank <= k
                )
                / sum(1 for r in runs if r.expected),
                3,
            )
            for k in (1, 3)
        },
        # Separabilidad: coseno del mejor fragmento correcto vs. el mejor fragmento
        # de las preguntas sin respuesta. Si se solapan, ningún umbral absoluto las separa.
        "separation": {
            "answerable_top_correct_vector_min": round(
                min(
                    max((h.vector for h in r.hybrid if _matches(h, r.expected)), default=0.0)
                    for r in runs
                    if r.expected
                ),
                4,
            ),
            "unanswerable_top_vector_max": round(
                max(
                    (
                        max((h.vector for h in r.hybrid), default=0.0)
                        for r in runs
                        if not r.expected
                    ),
                    default=0.0,
                ),
                4,
            ),
        },
        "best": {name: _best(rows) for name, rows in study.items()},
        # La grilla doble completa pesa decenas de MB: se guarda solo la curva de la
        # regla de producción, que es la que se usa para elegir el umbral.
        "production_rule_curve": study["production_rule"],
        "per_question": [
            {
                "id": r.id,
                "kind": r.kind,
                "hybrid_rank": _rank_of_first_match(r.hybrid, r.expected) if r.expected else None,
                "top": [
                    {
                        "document": h.document,
                        "pages": [h.page_from, h.page_to],
                        "vector": round(h.vector, 4),
                        "bm25": round(h.bm25, 3),
                    }
                    for h in r.hybrid[:3]
                ],
            }
            for r in runs
        ],
    }


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _render(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Spike — modelo de embeddings, fragmento y umbral",
        "",
        "> Generado por `scripts/eval_company_knowledge.py` sobre el set sintético de",
        "> `tests/fixtures/company_knowledge/eval/` (8 documentos MD/TXT/PDF, 30 preguntas:",
        "> 20 parafraseadas, 5 con términos exactos, 5 sin respuesta). Top-k = 6.",
        "",
        "## Recuperación por modo",
        "",
        "| Modelo | Fragmento | Vectorial recall@6/MRR | BM25 recall@6/MRR | Híbrido recall@6/MRR | Híbrido @1 / @3 | Fragmentos |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        m, at = r["metrics"], r["hybrid_recall_at"]
        lines.append(
            f"| `{r['model']}` | {r['chunk_tokens']} | {_pct(m['vector']['recall'])} / {m['vector']['mrr']} | "
            f"{_pct(m['bm25']['recall'])} / {m['bm25']['mrr']} | {_pct(m['hybrid']['recall'])} / {m['hybrid']['mrr']} | "
            f"{_pct(at['1'])} / {_pct(at['3'])} | {r['chunks']} |"
        )
    lines += [
        "",
        "## Separabilidad del coseno",
        "",
        "| Modelo | Fragmento | Peor coseno del fragmento correcto | Mejor coseno en preguntas sin respuesta | ¿Separables? |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        s = r["separation"]
        low, high = s["answerable_top_correct_vector_min"], s["unanswerable_top_vector_max"]
        lines.append(
            f"| `{r['model']}` | {r['chunk_tokens']} | {low} | {high} | {'sí' if low > high else 'no (se solapan)'} |"
        )
    lines += [
        "",
        "## Costo",
        "",
        "| Modelo | Fragmento | Indexación ms/página | p95 consulta ms | Memoria índice | Modelo en disco |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| `{r['model']}` | {r['chunk_tokens']} | {r['index_ms_per_page']} | {r['query_p95_ms']} | "
            f"{r['index_memory_bytes'] / 1024:.0f} KB | {r['model_disk_bytes'] / 1024 / 1024:.0f} MB |"
        )
    lines += [
        "",
        "## Filtrado: respuestas conservadas vs. preguntas sin respuesta vaciadas",
        "",
        "Mejor combinación por estrategia (prioriza no perder respuestas):",
        "",
        "| Modelo | Fragmento | Regla actual (vector ≥ t o BM25 > 0) | Solo vector ≥ t | Doble umbral |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        b = r["best"]
        p, v, d = b["production_rule"], b["vector_only"], b["dual"]
        lines.append(
            f"| `{r['model']}` | {r['chunk_tokens']} | t={p['t']}: {_pct(p['recall'])} / {_pct(p['rejection'])} | "
            f"t={v['t']}: {_pct(v['recall'])} / {_pct(v['rejection'])} | "
            f"bajo={d['t_low']} alto={d['t_high']} bm25>{d['bm25_min']}: {_pct(d['recall'])} / {_pct(d['rejection'])} |"
        )
    return "\n".join(lines) + "\n"


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--chunk-tokens", nargs="+", type=int, default=DEFAULT_CHUNK_TOKENS)
    parser.add_argument("--download", action="store_true", help="Descarga los modelos que falten.")
    parser.add_argument(
        "--long",
        action="store_true",
        help="Documentos largos: MD/TXT con relleno entre párrafos (sin PDF). Mide el truncamiento.",
    )
    parser.add_argument(
        "--out", help="Nombre del informe (misma carpeta). Por defecto, según el modo."
    )
    args = parser.parse_args()
    questions = json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))["questions"]
    report = REPORT
    if args.long:
        questions = [
            q for q in questions if all(not e["document"].endswith(".pdf") for e in q["expected"])
        ]
        report = REPORT.with_name("spike-modelo-largos-resultados.md")

    if args.out:
        report = REPORT.with_name(args.out)
    gemini_key = (
        await resolve_gemini_key() if any(m.startswith("gemini/") for m in args.models) else None
    )

    results: list[dict[str, Any]] = []
    for model in args.models:
        if args.download and not model.startswith("gemini/"):
            print(f"Preparando {model}…", flush=True)
            download_embedding_model(model, models_root(""))
        for chunk_tokens in args.chunk_tokens:
            print(f"Evaluando {model} con fragmento {chunk_tokens}…", flush=True)
            result = await _evaluate(model, chunk_tokens, questions, args.long, gemini_key)
            m = result["metrics"]["hybrid"]
            print(
                f"  híbrido recall={m['recall']} mrr={m['mrr']} · fallidos={result['failed_documents']}",
                flush=True,
            )
            results.append(result)

    report.parent.mkdir(parents=True, exist_ok=True)
    report.with_suffix(".json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report.write_text(_render(results), encoding="utf-8")
    print(f"Informe: {report}")


if __name__ == "__main__":
    asyncio.run(_main())
