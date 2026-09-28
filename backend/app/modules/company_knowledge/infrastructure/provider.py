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
from app.modules.chat.domain.interfaces import ActiveProviderResolver
from app.modules.company_knowledge.application.use_cases import (
    AiReadingLimits,
    CrawlWebSourceUseCase,
    ProcessNextCompanyDocumentUseCase,
    ReadPdfPagesUseCase,
)
from app.modules.company_knowledge.domain.interfaces import (
    AiReaderProvider,
    ContentExtractor,
    DocumentPageRepository,
    DocumentRepository,
    KnowledgeSettingsRepository,
    PageDiscoverer,
    WebFetcher,
    WebSourceRepository,
)
from app.modules.company_knowledge.infrastructure.ai_reading import (
    PROMPT_VERSION,
    ActiveProviderAiReaderProvider,
)
from app.modules.company_knowledge.infrastructure.chunking.structural_chunker import (
    StructuralChunker,
)
from app.modules.company_knowledge.infrastructure.embeddings import (
    FastEmbedEmbedder,
    models_root,
)
from app.modules.company_knowledge.infrastructure.extraction import (
    DispatchTextExtractor,
    PypdfPageAnalyzer,
)
from app.modules.company_knowledge.infrastructure.index import (
    InMemoryDocumentIndex,
    SearchSettings,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_document_repository import (  # noqa: E501
    SqlAlchemyDocumentRepository,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_page_repository import (  # noqa: E501
    SqlAlchemyDocumentPageRepository,
    SqlAlchemyKnowledgeSettingsRepository,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_web_source_repository import (  # noqa: E501
    SqlAlchemyWebSourceRepository,
)
from app.modules.company_knowledge.infrastructure.processing import (
    CompanyDocumentWorker,
    PipelineDocumentProcessor,
)
from app.modules.company_knowledge.infrastructure.web.content_extractor import (
    HybridContentExtractor,
)
from app.modules.company_knowledge.infrastructure.web.discovery import (
    SitemapAndLinksDiscoverer,
)
from app.modules.company_knowledge.infrastructure.web.safe_http import SafeHttpFetcher
from app.modules.company_knowledge.infrastructure.web.worker import WebSourceWorker
from app.modules.llm_providers.infrastructure.active_provider_resolver import (
    get_active_provider_resolver,
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
    # Lectura de PDF con IA. `readers` es `None` si el resolver de
    # proveedores no arrancó (tests que no pasan por el `lifespan`).
    pages: DocumentPageRepository | None = None
    knowledge_settings: KnowledgeSettingsRepository | None = None
    readers: AiReaderProvider | None = None
    # Importar desde la web (Fase 5).
    web_sources: WebSourceRepository | None = None
    web_fetcher: WebFetcher | None = None
    web_discoverer: PageDiscoverer | None = None
    web_extractor: ContentExtractor | None = None
    web_executor: ThreadPoolExecutor | None = None
    web_worker: WebSourceWorker | None = None

    def notify_worker(self) -> None:
        if self.worker is not None:
            self.worker.notify()

    def notify_web_worker(self) -> None:
        if self.web_worker is not None:
            self.web_worker.notify()


_runtime: CompanyKnowledgeRuntime | None = None


def _active_provider_resolver() -> ActiveProviderResolver | None:
    try:
        return get_active_provider_resolver()
    except RuntimeError:
        return None


def build_runtime(settings: Settings) -> CompanyKnowledgeRuntime:
    repository = SqlAlchemyDocumentRepository(get_agent_sessionmaker())
    pages = SqlAlchemyDocumentPageRepository(get_agent_sessionmaker())
    knowledge_settings = SqlAlchemyKnowledgeSettingsRepository(get_agent_sessionmaker())
    resolver = _active_provider_resolver()
    readers = (
        None
        if resolver is None
        else ActiveProviderAiReaderProvider(
            resolver, git_bash_path=settings.claude_code_git_bash_path
        )
    )
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
        pdf_reader = (
            None
            if readers is None
            else ReadPdfPagesUseCase(
                analyzer=PypdfPageAnalyzer(settings.company_docs_max_pages),
                pages=pages,
                settings=knowledge_settings,
                readers=readers,
                executor=ingest_executor,
                prompt_version=PROMPT_VERSION,
                limits=AiReadingLimits(
                    concurrency=settings.company_docs_ai_concurrency,
                    pages_per_request=settings.company_docs_ai_pages_per_request,
                    max_request_bytes=settings.company_docs_ai_max_request_mb * 1024 * 1024,
                    timeout_s=settings.company_docs_ai_timeout_s,
                    retry_attempts=settings.company_docs_ai_retry_attempts,
                    retry_base_delay_s=settings.company_docs_ai_retry_base_delay_s,
                ),
            )
        )
        worker = CompanyDocumentWorker(
            repository=repository,
            use_case=ProcessNextCompanyDocumentUseCase(
                repository,
                processor,
                settings.company_docs_max_total_chunks,
                index,
                pdf_reader,
            ),
            embedding_model=embedder.model_name,
        )
    runtime = CompanyKnowledgeRuntime(
        repository=repository,
        index=index,
        worker=worker,
        ingest_executor=ingest_executor,
        search_executor=search_executor,
        search_limit=settings.company_docs_search_limit,
        pages=pages,
        knowledge_settings=knowledge_settings,
        readers=readers,
    )
    _build_web(runtime, settings)
    return runtime


def _build_web(runtime: CompanyKnowledgeRuntime, settings: Settings) -> None:
    """Fuentes web: descarga simple con guarda SSRF, extracción y worker."""
    fetcher = SafeHttpFetcher(
        timeout_s=settings.company_web_fetch_timeout_s,
        max_bytes=settings.company_web_max_page_mb * 1024 * 1024,
        allowed_private_hosts=settings.company_web_allowed_private_hosts,
    )
    discoverer = SitemapAndLinksDiscoverer(
        fetcher,
        max_depth=settings.company_web_max_depth,
        request_delay_s=settings.company_web_request_delay_s,
    )
    extractor = HybridContentExtractor()
    sources = SqlAlchemyWebSourceRepository(get_agent_sessionmaker())
    # Hilo propio para la extracción: no compite con los embeddings.
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="company-web-extract")
    runtime.web_sources = sources
    runtime.web_fetcher = fetcher
    runtime.web_discoverer = discoverer
    runtime.web_extractor = extractor
    runtime.web_executor = executor
    if settings.company_docs_worker_enabled:
        runtime.web_worker = WebSourceWorker(
            repository=sources,
            use_case=CrawlWebSourceUseCase(
                sources=sources,
                documents=runtime.repository,
                fetcher=fetcher,
                discoverer=discoverer,
                extractor=extractor,
                executor=executor,
                request_delay_s=settings.company_web_request_delay_s,
                notifier=runtime.notify_worker,
                index=runtime.index,
            ),
            refresh_window=settings.company_web_refresh_window,
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
        if runtime.web_worker is not None:
            await runtime.web_worker.start()
    except Exception:
        logger.exception("company_docs_start_failed")
        _shutdown_executors(runtime)
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
    if runtime.web_worker is not None:
        await runtime.web_worker.stop()
    _shutdown_executors(runtime)
    _runtime = None


def _shutdown_executors(runtime: CompanyKnowledgeRuntime) -> None:
    runtime.ingest_executor.shutdown(wait=False, cancel_futures=True)
    runtime.search_executor.shutdown(wait=False, cancel_futures=True)
    if runtime.web_executor is not None:
        runtime.web_executor.shutdown(wait=False, cancel_futures=True)


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
