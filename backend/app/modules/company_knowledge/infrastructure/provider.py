"""Singletons de proceso del módulo `company_knowledge`.

Mismo patrón que `knowledge/infrastructure/catalog_provider.py`: se arma
una vez en el `lifespan` y se accede con getters. El índice y el worker
viven en memoria del proceso, por eso SAVI corre con un solo worker de
uvicorn (supuesto de la Fase 1 de plataforma).
"""

import asyncio
import contextlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.infrastructure.config.settings import Settings
from app.infrastructure.database import get_agent_sessionmaker
from app.modules.company_knowledge.application.use_cases import (
    ProcessNextCompanyDocumentUseCase,
)
from app.modules.company_knowledge.domain.interfaces import DocumentRepository
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
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_document_repository import (  # noqa: E501
    SqlAlchemyDocumentRepository,
)
from app.modules.company_knowledge.infrastructure.processing import (
    CompanyDocumentWorker,
    PipelineDocumentProcessor,
)

logger = logging.getLogger(__name__)


@dataclass
class CompanyKnowledgeRuntime:
    repository: DocumentRepository
    index: InMemoryDocumentIndex
    worker: CompanyDocumentWorker | None
    ingest_executor: ThreadPoolExecutor
    search_executor: ThreadPoolExecutor
    search_limit: int = 6
    load_task: asyncio.Task[None] | None = None

    def notify_worker(self) -> None:
        if self.worker is not None:
            self.worker.notify()


_runtime: CompanyKnowledgeRuntime | None = None


def build_runtime(settings: Settings) -> CompanyKnowledgeRuntime:
    repository = SqlAlchemyDocumentRepository(get_agent_sessionmaker())
    # Hilos de ONNX acotados: la mitad de los núcleos queda para el chat.
    threads = max(1, (os.cpu_count() or 2) // 2)
    embedder = FastEmbedEmbedder(
        settings.company_docs_embedding_model,
        models_root(settings.company_docs_model_dir),
        threads,
    )
    ingest_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="company-docs-ingest")
    search_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="company-docs-search")
    index = InMemoryDocumentIndex(
        repository=repository,
        embedder=embedder,
        build_executor=ingest_executor,
        search_executor=search_executor,
        settings=SearchSettings(
            candidates=settings.company_docs_search_candidates,
            limit=settings.company_docs_search_limit,
            max_per_document=settings.company_docs_search_max_per_document,
            max_context_chars=settings.company_docs_max_context_chars,
            min_similarity=settings.company_docs_min_similarity,
        ),
    )
    worker: CompanyDocumentWorker | None = None
    if settings.company_docs_worker_enabled:
        processor = PipelineDocumentProcessor(
            extractor=DispatchTextExtractor(settings.company_docs_max_pages),
            chunker=StructuralChunker(
                settings.company_docs_chunk_tokens, settings.company_docs_chunk_overlap
            ),
            embedder=embedder,
            executor=ingest_executor,
            max_chunks_per_document=settings.company_docs_max_chunks_per_doc,
        )
        worker = CompanyDocumentWorker(
            repository=repository,
            use_case=ProcessNextCompanyDocumentUseCase(
                repository,
                processor,
                settings.company_docs_max_total_chunks,
                index,
            ),
            embedding_model=embedder.model_name,
        )
    return CompanyKnowledgeRuntime(
        repository=repository,
        index=index,
        worker=worker,
        ingest_executor=ingest_executor,
        search_executor=search_executor,
        search_limit=settings.company_docs_search_limit,
    )


async def start_company_knowledge(settings: Settings) -> CompanyKnowledgeRuntime | None:
    """Arranca el módulo. Si falla, SAVI sigue funcionando sin documentos.

    Un problema acá (tablas sin migrar, BD caída al arrancar) no puede
    tumbar el chat, que no depende de este módulo.
    """
    global _runtime
    runtime = build_runtime(settings)
    try:
        if runtime.worker is not None:
            await runtime.worker.start()
    except Exception:
        logger.exception("company_docs_start_failed")
        runtime.ingest_executor.shutdown(wait=False, cancel_futures=True)
        runtime.search_executor.shutdown(wait=False, cancel_futures=True)
        return None
    # La carga del índice no bloquea el arranque de la API: mientras corre,
    # la búsqueda devuelve vacío y el resto de SAVI funciona igual.
    runtime.load_task = asyncio.create_task(_load_index(runtime), name="company-docs-index-load")
    _runtime = runtime
    return runtime


async def stop_company_knowledge() -> None:
    global _runtime
    runtime = _runtime
    if runtime is None:
        return
    if runtime.load_task is not None:
        runtime.load_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await runtime.load_task
    if runtime.worker is not None:
        await runtime.worker.stop()
    runtime.ingest_executor.shutdown(wait=False, cancel_futures=True)
    runtime.search_executor.shutdown(wait=False, cancel_futures=True)
    _runtime = None


async def _load_index(runtime: CompanyKnowledgeRuntime) -> None:
    try:
        await runtime.index.load()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("company_docs_index_load_failed")


def get_company_knowledge_runtime() -> CompanyKnowledgeRuntime | None:
    """`None` si el módulo no arrancó (tests que no pasan por el `lifespan`)."""
    return _runtime
