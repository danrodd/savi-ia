"""DI del módulo `company_knowledge`."""

from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import get_agent_sessionmaker
from app.modules.company_knowledge.application.use_cases import (
    DeleteCompanyDocumentUseCase,
    DownloadCompanyDocumentUseCase,
    GetAiReadingSettingsUseCase,
    GetCompanyDocumentUsageUseCase,
    GetCompanyDocumentUseCase,
    ListCompanyDocumentsUseCase,
    ReadCompanyDocumentWithAiUseCase,
    ReplaceCompanyDocumentUseCase,
    ReprocessCompanyDocumentUseCase,
    TestDocumentSearchUseCase,
    UpdateAiReadingSettingsUseCase,
    UpdateCompanyDocumentUseCase,
    UploadCompanyDocumentUseCase,
)
from app.modules.company_knowledge.domain.interfaces import (
    AiReaderAvailability,
    AiReaderProvider,
    DocumentIndex,
    DocumentPageRepository,
    KnowledgeSettingsRepository,
    PdfPageReader,
)
from app.modules.company_knowledge.infrastructure.ai_reading import (
    ActiveProviderAiReaderProvider,
)
from app.modules.company_knowledge.infrastructure.extraction import ContentMediaTypeSniffer
from app.modules.company_knowledge.infrastructure.http.repository_dependency import (
    DocumentRepositoryDep,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_page_repository import (  # noqa: E501
    SqlAlchemyDocumentPageRepository,
    SqlAlchemyKnowledgeSettingsRepository,
)
from app.modules.company_knowledge.infrastructure.provider import (
    get_company_knowledge_runtime,
)
from app.modules.conversations.infrastructure.http.dependencies import (
    ConversationRepositoryDep,
)
from app.modules.erp_databases.infrastructure.http.dependencies import (
    ErpDatabaseRepositoryDep,
    ResolveModulesForDatabaseUseCaseDep,
)
from app.modules.llm_providers.infrastructure.active_provider_resolver import (
    get_active_provider_resolver,
)

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_document_index() -> DocumentIndex | None:
    runtime = get_company_knowledge_runtime()
    return None if runtime is None else runtime.index


def _notify_worker() -> None:
    runtime = get_company_knowledge_runtime()
    if runtime is not None:
        runtime.notify_worker()


DocumentIndexDep = Annotated[DocumentIndex | None, Depends(get_document_index)]


def get_page_repository() -> DocumentPageRepository:
    runtime = get_company_knowledge_runtime()
    if runtime is not None and runtime.pages is not None:
        return runtime.pages
    return SqlAlchemyDocumentPageRepository(get_agent_sessionmaker())


def get_knowledge_settings_repository() -> KnowledgeSettingsRepository:
    runtime = get_company_knowledge_runtime()
    if runtime is not None and runtime.knowledge_settings is not None:
        return runtime.knowledge_settings
    return SqlAlchemyKnowledgeSettingsRepository(get_agent_sessionmaker())


class _NoReaders(AiReaderProvider):
    """Sin resolver de proveedores (el `lifespan` no corrió): nada que leer."""

    async def availability(self) -> AiReaderAvailability:
        return AiReaderAvailability(
            available=False, reason="No hay un proveedor de IA configurado."
        )

    async def build_reader(self) -> PdfPageReader | None:
        return None


def get_ai_reader_provider(settings: SettingsDep) -> AiReaderProvider:
    runtime = get_company_knowledge_runtime()
    if runtime is not None and runtime.readers is not None:
        return runtime.readers
    try:
        resolver = get_active_provider_resolver()
    except RuntimeError:
        return _NoReaders()
    return ActiveProviderAiReaderProvider(
        resolver, git_bash_path=settings.claude_code_git_bash_path
    )


PageRepositoryDep = Annotated[DocumentPageRepository, Depends(get_page_repository)]
KnowledgeSettingsRepositoryDep = Annotated[
    KnowledgeSettingsRepository, Depends(get_knowledge_settings_repository)
]
AiReaderProviderDep = Annotated[AiReaderProvider, Depends(get_ai_reader_provider)]


def get_upload_use_case(
    repository: DocumentRepositoryDep,
    settings: SettingsDep,
    erp_repository: ErpDatabaseRepositoryDep,
) -> UploadCompanyDocumentUseCase:
    return UploadCompanyDocumentUseCase(
        repository, ContentMediaTypeSniffer(), settings, erp_repository, _notify_worker
    )


def get_update_use_case(
    repository: DocumentRepositoryDep,
    erp_repository: ErpDatabaseRepositoryDep,
    index: DocumentIndexDep,
) -> UpdateCompanyDocumentUseCase:
    return UpdateCompanyDocumentUseCase(repository, erp_repository, index)


def get_replace_use_case(
    repository: DocumentRepositoryDep, settings: SettingsDep, index: DocumentIndexDep
) -> ReplaceCompanyDocumentUseCase:
    return ReplaceCompanyDocumentUseCase(
        repository, ContentMediaTypeSniffer(), settings, _notify_worker, index
    )


def get_reprocess_use_case(
    repository: DocumentRepositoryDep, index: DocumentIndexDep
) -> ReprocessCompanyDocumentUseCase:
    return ReprocessCompanyDocumentUseCase(repository, _notify_worker, index)


def get_read_with_ai_use_case(
    repository: DocumentRepositoryDep,
    pages: PageRepositoryDep,
    knowledge_settings: KnowledgeSettingsRepositoryDep,
    readers: AiReaderProviderDep,
    index: DocumentIndexDep,
) -> ReadCompanyDocumentWithAiUseCase:
    return ReadCompanyDocumentWithAiUseCase(
        repository, pages, knowledge_settings, readers, _notify_worker, index
    )


def get_ai_reading_settings_use_case(
    knowledge_settings: KnowledgeSettingsRepositoryDep,
    readers: AiReaderProviderDep,
    pages: PageRepositoryDep,
) -> GetAiReadingSettingsUseCase:
    return GetAiReadingSettingsUseCase(knowledge_settings, readers, pages)


def get_update_ai_reading_settings_use_case(
    knowledge_settings: KnowledgeSettingsRepositoryDep,
    readers: AiReaderProviderDep,
    pages: PageRepositoryDep,
) -> UpdateAiReadingSettingsUseCase:
    return UpdateAiReadingSettingsUseCase(knowledge_settings, readers, pages)


def get_delete_use_case(
    repository: DocumentRepositoryDep, index: DocumentIndexDep
) -> DeleteCompanyDocumentUseCase:
    return DeleteCompanyDocumentUseCase(repository, index)


def get_list_use_case(repository: DocumentRepositoryDep) -> ListCompanyDocumentsUseCase:
    return ListCompanyDocumentsUseCase(repository)


def get_get_use_case(repository: DocumentRepositoryDep) -> GetCompanyDocumentUseCase:
    return GetCompanyDocumentUseCase(repository)


def get_usage_use_case(
    repository: DocumentRepositoryDep, settings: SettingsDep, index: DocumentIndexDep
) -> GetCompanyDocumentUsageUseCase:
    return GetCompanyDocumentUsageUseCase(
        repository,
        chunk_limit=settings.company_docs_max_total_chunks,
        embedding_model=settings.company_docs_embedding_model,
        index=index,
    )


UploadUseCaseDep = Annotated[UploadCompanyDocumentUseCase, Depends(get_upload_use_case)]
UpdateUseCaseDep = Annotated[UpdateCompanyDocumentUseCase, Depends(get_update_use_case)]
ReplaceUseCaseDep = Annotated[ReplaceCompanyDocumentUseCase, Depends(get_replace_use_case)]
ReprocessUseCaseDep = Annotated[ReprocessCompanyDocumentUseCase, Depends(get_reprocess_use_case)]
DeleteUseCaseDep = Annotated[DeleteCompanyDocumentUseCase, Depends(get_delete_use_case)]
ListUseCaseDep = Annotated[ListCompanyDocumentsUseCase, Depends(get_list_use_case)]
GetUseCaseDep = Annotated[GetCompanyDocumentUseCase, Depends(get_get_use_case)]
UsageUseCaseDep = Annotated[GetCompanyDocumentUsageUseCase, Depends(get_usage_use_case)]
ReadWithAiUseCaseDep = Annotated[
    ReadCompanyDocumentWithAiUseCase, Depends(get_read_with_ai_use_case)
]
AiReadingSettingsUseCaseDep = Annotated[
    GetAiReadingSettingsUseCase, Depends(get_ai_reading_settings_use_case)
]
UpdateAiReadingSettingsUseCaseDep = Annotated[
    UpdateAiReadingSettingsUseCase, Depends(get_update_ai_reading_settings_use_case)
]


def get_download_use_case(
    repository: DocumentRepositoryDep,
    conversations: ConversationRepositoryDep,
    access_resolver: ResolveModulesForDatabaseUseCaseDep,
    settings: SettingsDep,
) -> DownloadCompanyDocumentUseCase:
    return DownloadCompanyDocumentUseCase(
        repository=repository,
        conversations=conversations,
        access_resolver=access_resolver,
        savi_admin_logins=settings.savi_admin_logins_set,
    )


def get_search_test_use_case(
    repository: DocumentRepositoryDep,
    index: DocumentIndexDep,
    access_resolver: ResolveModulesForDatabaseUseCaseDep,
    settings: SettingsDep,
) -> TestDocumentSearchUseCase:
    return TestDocumentSearchUseCase(
        index=index,
        repository=repository,
        access_resolver=access_resolver,
        savi_admin_logins=settings.savi_admin_logins_set,
        embedding_model=settings.company_docs_embedding_model,
        limit=settings.company_docs_search_limit,
    )


DownloadUseCaseDep = Annotated[DownloadCompanyDocumentUseCase, Depends(get_download_use_case)]
SearchTestUseCaseDep = Annotated[TestDocumentSearchUseCase, Depends(get_search_test_use_case)]
