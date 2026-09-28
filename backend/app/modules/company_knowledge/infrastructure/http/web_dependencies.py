"""DI de las fuentes web (Fase 5).

Usa las piezas del runtime (fetcher con guarda SSRF, worker de rastreo).
Sin runtime (tests que no pasan por el `lifespan`) se arman al vuelo.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import Depends

from app.infrastructure.database import get_agent_sessionmaker
from app.modules.company_knowledge.application.use_cases import (
    CreateWebSourceUseCase,
    DeleteWebSourceUseCase,
    GetWebSourceUseCase,
    ListWebSourcesUseCase,
    PreviewWebSourceUseCase,
    RefreshWebSourceUseCase,
    UpdateWebSourceUseCase,
)
from app.modules.company_knowledge.domain.interfaces import (
    ContentExtractor,
    PageDiscoverer,
    WebFetcher,
    WebSourceRepository,
)
from app.modules.company_knowledge.infrastructure.http.dependencies import (
    DocumentIndexDep,
    SettingsDep,
)
from app.modules.company_knowledge.infrastructure.http.repository_dependency import (
    DocumentRepositoryDep,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_web_source_repository import (  # noqa: E501
    SqlAlchemyWebSourceRepository,
)
from app.modules.company_knowledge.infrastructure.provider import (
    get_company_knowledge_runtime,
)
from app.modules.company_knowledge.infrastructure.web.content_extractor import (
    HybridContentExtractor,
)
from app.modules.company_knowledge.infrastructure.web.discovery import (
    SitemapAndLinksDiscoverer,
)
from app.modules.company_knowledge.infrastructure.web.safe_http import SafeHttpFetcher
from app.modules.erp_databases.infrastructure.http.dependencies import ErpDatabaseRepositoryDep

# Solo sin runtime: un hilo compartido para las vistas previas de los tests.
_fallback_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="company-web-preview")


def _notify_web_worker() -> None:
    runtime = get_company_knowledge_runtime()
    if runtime is not None:
        runtime.notify_web_worker()


def get_web_source_repository() -> WebSourceRepository:
    runtime = get_company_knowledge_runtime()
    if runtime is not None and runtime.web_sources is not None:
        return runtime.web_sources
    return SqlAlchemyWebSourceRepository(get_agent_sessionmaker())


def get_web_fetcher(settings: SettingsDep) -> WebFetcher:
    runtime = get_company_knowledge_runtime()
    if runtime is not None and runtime.web_fetcher is not None:
        return runtime.web_fetcher
    return SafeHttpFetcher(
        timeout_s=settings.company_web_fetch_timeout_s,
        max_bytes=settings.company_web_max_page_mb * 1024 * 1024,
        allowed_private_hosts=settings.company_web_allowed_private_hosts,
    )


WebSourceRepositoryDep = Annotated[WebSourceRepository, Depends(get_web_source_repository)]
WebFetcherDep = Annotated[WebFetcher, Depends(get_web_fetcher)]


def get_web_discoverer(fetcher: WebFetcherDep, settings: SettingsDep) -> PageDiscoverer:
    runtime = get_company_knowledge_runtime()
    if runtime is not None and runtime.web_discoverer is not None:
        return runtime.web_discoverer
    return SitemapAndLinksDiscoverer(
        fetcher,
        max_depth=settings.company_web_max_depth,
        request_delay_s=settings.company_web_request_delay_s,
    )


def get_web_extractor() -> ContentExtractor:
    runtime = get_company_knowledge_runtime()
    if runtime is not None and runtime.web_extractor is not None:
        return runtime.web_extractor
    return HybridContentExtractor()


def get_preview_use_case(
    fetcher: WebFetcherDep,
    discoverer: Annotated[PageDiscoverer, Depends(get_web_discoverer)],
    extractor: Annotated[ContentExtractor, Depends(get_web_extractor)],
) -> PreviewWebSourceUseCase:
    runtime = get_company_knowledge_runtime()
    executor = (
        runtime.web_executor
        if runtime is not None and runtime.web_executor is not None
        else _fallback_executor
    )
    return PreviewWebSourceUseCase(fetcher, discoverer, extractor, executor)


def get_create_web_source_use_case(
    repository: WebSourceRepositoryDep,
    fetcher: WebFetcherDep,
    erp_repository: ErpDatabaseRepositoryDep,
    settings: SettingsDep,
) -> CreateWebSourceUseCase:
    return CreateWebSourceUseCase(
        repository,
        fetcher,
        erp_repository,
        max_sources=settings.company_web_max_sources,
        max_pages_limit=settings.company_web_max_pages_per_source,
        notifier=_notify_web_worker,
    )


def get_update_web_source_use_case(
    repository: WebSourceRepositoryDep,
    documents: DocumentRepositoryDep,
    erp_repository: ErpDatabaseRepositoryDep,
    settings: SettingsDep,
    index: DocumentIndexDep,
) -> UpdateWebSourceUseCase:
    return UpdateWebSourceUseCase(
        repository,
        documents,
        erp_repository,
        max_pages_limit=settings.company_web_max_pages_per_source,
        index=index,
    )


def get_delete_web_source_use_case(
    repository: WebSourceRepositoryDep, documents: DocumentRepositoryDep, index: DocumentIndexDep
) -> DeleteWebSourceUseCase:
    return DeleteWebSourceUseCase(repository, documents, index)


def get_refresh_web_source_use_case(repository: WebSourceRepositoryDep) -> RefreshWebSourceUseCase:
    return RefreshWebSourceUseCase(repository, _notify_web_worker)


def get_list_web_sources_use_case(repository: WebSourceRepositoryDep) -> ListWebSourcesUseCase:
    return ListWebSourcesUseCase(repository)


def get_web_source_use_case(repository: WebSourceRepositoryDep) -> GetWebSourceUseCase:
    return GetWebSourceUseCase(repository)


PreviewWebSourceUseCaseDep = Annotated[PreviewWebSourceUseCase, Depends(get_preview_use_case)]
CreateWebSourceUseCaseDep = Annotated[
    CreateWebSourceUseCase, Depends(get_create_web_source_use_case)
]
UpdateWebSourceUseCaseDep = Annotated[
    UpdateWebSourceUseCase, Depends(get_update_web_source_use_case)
]
DeleteWebSourceUseCaseDep = Annotated[
    DeleteWebSourceUseCase, Depends(get_delete_web_source_use_case)
]
RefreshWebSourceUseCaseDep = Annotated[
    RefreshWebSourceUseCase, Depends(get_refresh_web_source_use_case)
]
ListWebSourcesUseCaseDep = Annotated[ListWebSourcesUseCase, Depends(get_list_web_sources_use_case)]
GetWebSourceUseCaseDep = Annotated[GetWebSourceUseCase, Depends(get_web_source_use_case)]
