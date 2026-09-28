"""Índice híbrido en memoria: vectores + BM25, combinados con RRF.

Decisiones (spec Fase 2 §2):

- **Snapshots inmutables.** Toda mutación arma un snapshot nuevo y reemplaza
  la referencia con una asignación. Una búsqueda en curso sigue con el
  snapshot que tomó: sin locks en lectura ni carreras con el worker.
- **Postings por documento**, no un índice invertido global. Publicar un
  documento no re-tokeniza los demás; el snapshot solo vuelve a apilar los
  vectores y a sumar las frecuencias de documento.
- **Filtro de permisos ANTES de rankear.** Los pasos vectorial y léxico solo
  ven filas de documentos que `can_read` permite. No existe un camino que
  rankee todo y filtre después: un fragmento sin permiso nunca llega al
  modelo porque nunca sale de acá.
"""

import asyncio
import logging
import math
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from uuid import UUID

import numpy as np

from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
    DocumentChunk,
)
from app.modules.company_knowledge.domain.entities.document_access_view import (
    DocumentAccessView,
)
from app.modules.company_knowledge.domain.exceptions import EmbedderUnavailableError
from app.modules.company_knowledge.domain.interfaces import (
    ChunkHit,
    DocumentIndex,
    DocumentRepository,
    Embedder,
    IndexedDocument,
    IndexStatus,
)
from app.modules.company_knowledge.domain.services.document_access_policy import (
    DocumentAccessContext,
    can_read,
)
from app.modules.company_knowledge.infrastructure.embeddings.vector_codec import (
    bytes_to_vector,
)
from app.modules.company_knowledge.infrastructure.index.tokenizer import tokenize

logger = logging.getLogger(__name__)

_RRF_K = 60
_BM25_K1 = 1.2
_BM25_B = 0.75


@dataclass(frozen=True, slots=True)
class SearchSettings:
    candidates: int = 50
    limit: int = 6
    max_per_document: int = 3
    max_context_chars: int = 6000
    min_similarity: float = 0.3


@dataclass(frozen=True, slots=True)
class _ChunkMeta:
    ordinal: int
    text: str
    heading: str | None
    page_from: int | None
    page_to: int | None


@dataclass(frozen=True, slots=True)
class _DocData:
    view: DocumentAccessView
    vectors: np.ndarray  # (n, dim) float32 normalizados
    chunks: tuple[_ChunkMeta, ...]
    lengths: np.ndarray  # (n,) largo en tokens
    # término → [(índice local del fragmento, frecuencia)]
    postings: dict[str, list[tuple[int, int]]]

    @property
    def text_bytes(self) -> int:
        return sum(len(chunk.text) for chunk in self.chunks)


@dataclass(frozen=True, slots=True)
class _Snapshot:
    docs: tuple[_DocData, ...] = ()
    offsets: tuple[int, ...] = ()
    vectors: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    row_doc: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int32))
    df: dict[str, int] = field(default_factory=dict[str, int])
    total_chunks: int = 0
    avg_length: float = 1.0


class InMemoryDocumentIndex(DocumentIndex):
    def __init__(
        self,
        *,
        repository: DocumentRepository,
        embedder: Embedder,
        build_executor: ThreadPoolExecutor,
        search_executor: ThreadPoolExecutor,
        settings: SearchSettings,
    ) -> None:
        self._repository = repository
        self._embedder = embedder
        self._build_executor = build_executor
        self._search_executor = search_executor
        self._settings = settings
        self._docs: dict[UUID, _DocData] = {}
        self._snapshot = _Snapshot()
        self._loaded = False
        self._lock = asyncio.Lock()

    # ── Carga y mutaciones ───────────────────────────────────────────────
    async def load(self) -> None:
        """Carga inicial. Mientras no termina, `search` devuelve vacío."""
        async with self._lock:
            documents = await self._repository.list_ready_for_index(self._embedder.model_name)
            for document in documents:
                chunks = await self._repository.list_chunks(document.id)
                self._docs[document.id] = await self._build_doc(document, chunks)
            await self._rebuild_snapshot()
            self._loaded = True
        logger.info(
            "company_docs_index_loaded documents=%s chunks=%s",
            len(self._docs),
            self._snapshot.total_chunks,
        )

    async def publish_document(self, document_id: UUID) -> None:
        """Sincroniza el documento desde la BD: lo carga si está listo, si no lo retira."""
        async with self._lock:
            document = await self._repository.get_by_id(document_id)
            if not self._indexable(document):
                if self._docs.pop(document_id, None) is not None:
                    await self._rebuild_snapshot()
                return
            assert document is not None  # noqa: S101 — garantizado por `_indexable`
            chunks = await self._repository.list_chunks(document_id)
            self._docs[document_id] = await self._build_doc(document, chunks)
            await self._rebuild_snapshot()

    async def update_metadata(self, document_id: UUID) -> None:
        async with self._lock:
            current = self._docs.get(document_id)
            document = await self._repository.get_by_id(document_id)
            if current is None:
                if not self._indexable(document):
                    return
                assert document is not None  # noqa: S101
                chunks = await self._repository.list_chunks(document_id)
                self._docs[document_id] = await self._build_doc(document, chunks)
            elif not self._indexable(document):
                del self._docs[document_id]
            else:
                assert document is not None  # noqa: S101
                # Solo cambia la vista de permisos y título: vectores y
                # postings se reutilizan tal cual.
                self._docs[document_id] = _DocData(
                    view=_view(document),
                    vectors=current.vectors,
                    chunks=current.chunks,
                    lengths=current.lengths,
                    postings=current.postings,
                )
            await self._rebuild_snapshot()

    async def remove_document(self, document_id: UUID) -> None:
        async with self._lock:
            if self._docs.pop(document_id, None) is not None:
                await self._rebuild_snapshot()

    def status(self) -> IndexStatus:
        snapshot = self._snapshot
        memory = int(snapshot.vectors.nbytes) + sum(doc.text_bytes for doc in snapshot.docs)
        return IndexStatus(
            loaded=self._loaded,
            chunks=snapshot.total_chunks,
            memory_bytes=memory,
            model=self._embedder.model_name,
        )

    # ── Búsqueda ─────────────────────────────────────────────────────────
    async def list_documents(self, ctx: DocumentAccessContext) -> list[IndexedDocument]:
        snapshot = self._snapshot
        if not self._loaded:
            return []
        documents = [
            IndexedDocument(
                document_id=doc.view.id,
                title=doc.view.title,
                version=doc.view.version,
                page_count=doc.view.page_count,
                updated_at=doc.view.updated_at,
                source_url=doc.view.source_url,
            )
            for doc in snapshot.docs
            if can_read(doc.view, ctx)
        ]
        return sorted(documents, key=lambda document: document.title.casefold())

    async def search(
        self, query: str, ctx: DocumentAccessContext, *, limit: int = 6
    ) -> list[ChunkHit]:
        snapshot = self._snapshot
        if not self._loaded or snapshot.total_chunks == 0 or not query.strip():
            return []

        # PASO INNEGOCIABLE: permisos antes de cualquier ranking.
        allowed = [i for i, doc in enumerate(snapshot.docs) if can_read(doc.view, ctx)]
        if not allowed:
            return []

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._search_executor, self._search_sync, snapshot, allowed, query, limit
        )

    def _search_sync(
        self, snapshot: _Snapshot, allowed: list[int], query: str, limit: int
    ) -> list[ChunkHit]:
        settings = self._settings
        vector_scores = self._vector_candidates(snapshot, allowed, query)
        bm25_scores = _bm25_candidates(snapshot, allowed, tokenize(query), settings.candidates)

        vector_ranked = sorted(vector_scores.items(), key=lambda item: item[1], reverse=True)
        bm25_ranked = sorted(bm25_scores.items(), key=lambda item: item[1], reverse=True)

        fused: dict[int, float] = {}
        for rank, (row, score) in enumerate(vector_ranked):
            # Umbral: una fila que solo trae similitud baja y ninguna
            # coincidencia léxica no es una respuesta, es ruido.
            if score < settings.min_similarity and row not in bm25_scores:
                continue
            fused[row] = fused.get(row, 0.0) + 1.0 / (_RRF_K + rank + 1)
        for rank, (row, _score) in enumerate(bm25_ranked):
            fused[row] = fused.get(row, 0.0) + 1.0 / (_RRF_K + rank + 1)

        hits: list[ChunkHit] = []
        per_document: Counter[int] = Counter()
        context_chars = 0
        for row, rrf in sorted(fused.items(), key=lambda item: item[1], reverse=True):
            doc_index = int(snapshot.row_doc[row])
            if per_document[doc_index] >= settings.max_per_document:
                continue
            doc = snapshot.docs[doc_index]
            chunk = doc.chunks[row - snapshot.offsets[doc_index]]
            if hits and context_chars + len(chunk.text) > settings.max_context_chars:
                break
            per_document[doc_index] += 1
            context_chars += len(chunk.text)
            hits.append(
                ChunkHit(
                    document_id=doc.view.id,
                    title=doc.view.title,
                    version=doc.view.version,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    page_from=chunk.page_from,
                    page_to=chunk.page_to,
                    heading=chunk.heading,
                    source_url=doc.view.source_url,
                    vector_score=vector_scores.get(row, 0.0),
                    bm25_score=bm25_scores.get(row, 0.0),
                    rrf_score=rrf,
                )
            )
            if len(hits) >= min(limit, settings.limit):
                break
        return hits

    def _vector_candidates(
        self, snapshot: _Snapshot, allowed: list[int], query: str
    ) -> dict[int, float]:
        try:
            query_vector = np.asarray(self._embedder.embed_query(query), dtype=np.float32)
        except EmbedderUnavailableError:
            # Sin modelo la búsqueda sigue funcionando solo con BM25.
            logger.warning("company_docs_search_embedder_unavailable")
            return {}
        if snapshot.vectors.shape[0] == 0 or query_vector.shape[0] != snapshot.vectors.shape[1]:
            return {}
        rows = np.nonzero(np.isin(snapshot.row_doc, np.asarray(allowed, dtype=np.int32)))[0]
        if rows.size == 0:
            return {}
        scores = snapshot.vectors[rows] @ query_vector
        top = min(self._settings.candidates, int(rows.size))
        best = np.argpartition(-scores, top - 1)[:top]
        return {int(rows[i]): float(scores[i]) for i in best}

    # ── Construcción ─────────────────────────────────────────────────────
    def _indexable(self, document: CompanyDocument | None) -> bool:
        return (
            document is not None
            and document.is_ready
            and document.embedding_model == self._embedder.model_name
        )

    async def _build_doc(
        self, document: CompanyDocument, chunks: Sequence[DocumentChunk]
    ) -> _DocData:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._build_executor, _build_doc_data, document, chunks)

    async def _rebuild_snapshot(self) -> None:
        docs = tuple(self._docs.values())
        loop = asyncio.get_running_loop()
        self._snapshot = await loop.run_in_executor(self._build_executor, _build_snapshot, docs)


def _view(document: CompanyDocument) -> DocumentAccessView:
    return DocumentAccessView.from_document(document, frozenset(document.database_ids))


def _build_doc_data(document: CompanyDocument, chunks: Sequence[DocumentChunk]) -> _DocData:
    ordered = sorted(chunks, key=lambda chunk: chunk.ordinal)
    metas: list[_ChunkMeta] = []
    vectors: list[np.ndarray] = []
    lengths: list[int] = []
    postings: dict[str, list[tuple[int, int]]] = {}
    for local, chunk in enumerate(ordered):
        metas.append(
            _ChunkMeta(
                ordinal=chunk.ordinal,
                text=chunk.text,
                heading=chunk.heading,
                page_from=chunk.page_from,
                page_to=chunk.page_to,
            )
        )
        vectors.append(bytes_to_vector(chunk.embedding))
        indexed_text = f"{chunk.heading}\n{chunk.text}" if chunk.heading else chunk.text
        counts = Counter(tokenize(indexed_text))
        lengths.append(max(1, sum(counts.values())))
        for term, frequency in counts.items():
            postings.setdefault(term, []).append((local, frequency))
    matrix = (
        np.vstack(vectors).astype(np.float32, copy=False)
        if vectors
        else np.zeros((0, 0), dtype=np.float32)
    )
    return _DocData(
        view=_view(document),
        vectors=matrix,
        chunks=tuple(metas),
        lengths=np.asarray(lengths, dtype=np.float32),
        postings=postings,
    )


def _build_snapshot(docs: tuple[_DocData, ...]) -> _Snapshot:
    if not docs:
        return _Snapshot()
    offsets: list[int] = []
    row_doc: list[np.ndarray] = []
    df: Counter[str] = Counter()
    total = 0
    total_length = 0.0
    matrices: list[np.ndarray] = []
    for index, doc in enumerate(docs):
        count = len(doc.chunks)
        offsets.append(total)
        row_doc.append(np.full(count, index, dtype=np.int32))
        if count:
            matrices.append(doc.vectors)
        total += count
        total_length += float(doc.lengths.sum())
        for term, entries in doc.postings.items():
            df[term] += len(entries)
    dims = {matrix.shape[1] for matrix in matrices}
    # Dimensiones mezcladas solo pasan si se cambió de modelo sin
    # reprocesar; `_indexable` ya lo impide, pero no se arriesga un crash.
    vectors = (
        np.vstack(matrices) if matrices and len(dims) == 1 else np.zeros((0, 0), dtype=np.float32)
    )
    return _Snapshot(
        docs=docs,
        offsets=tuple(offsets),
        vectors=vectors,
        row_doc=np.concatenate(row_doc) if row_doc else np.zeros(0, dtype=np.int32),
        df=dict(df),
        total_chunks=total,
        avg_length=total_length / total if total else 1.0,
    )


def _bm25_candidates(
    snapshot: _Snapshot, allowed: list[int], query_terms: list[str], candidates: int
) -> dict[int, float]:
    if not query_terms:
        return {}
    terms = set(query_terms)
    total = snapshot.total_chunks
    scores: dict[int, float] = {}
    for doc_index in allowed:
        doc = snapshot.docs[doc_index]
        offset = snapshot.offsets[doc_index]
        for term in terms:
            entries = doc.postings.get(term)
            if not entries:
                continue
            df = snapshot.df.get(term, 0)
            idf = math.log(1.0 + (total - df + 0.5) / (df + 0.5))
            for local, frequency in entries:
                length = float(doc.lengths[local])
                norm = frequency + _BM25_K1 * (1 - _BM25_B + _BM25_B * length / snapshot.avg_length)
                row = offset + local
                scores[row] = scores.get(row, 0.0) + idf * frequency * (_BM25_K1 + 1) / norm
    if len(scores) <= candidates:
        return scores
    best = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:candidates]
    return dict(best)
