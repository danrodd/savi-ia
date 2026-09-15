"""DI del módulo `company_knowledge`."""

from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.modules.company_knowledge.application.use_cases import (
    DeleteCompanyDocumentUseCase,
    DownloadCompanyDocumentUseCase,
    GetCompanyDocumentUsageUseCase,
    GetCompanyDocumentUseCase,
    ListCompanyDocumentsUseCase,
    ReplaceCompanyDocumentUseCase,
    ReprocessCompanyDocumentUseCase,
    TestDocumentSearchUseCase,
    UpdateCompanyDocumentUseCase,
    UploadCompanyDocumentUseCase,
)
from app.modules.company_knowledge.domain.interfaces import (
    DocumentIndex,
)
from app.modules.company_knowledge.infrastructure.extraction import ContentMediaTypeSniffer
from app.modules.company_knowledge.infrastructure.http.repository_dependency import (
    DocumentRepositoryDep,
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

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_document_index() -> DocumentIndex | None:
    runtime = get_company_knowledge_runtime()
    return None if runtime is None else runtime.index


def _notify_worker() -> None:
    runtime = get_company_knowledge_runtime()
    if runtime is not None:
        runtime.notify_worker()


DocumentIndexDep = Annotated[DocumentIndex | None, Depends(get_document_index)]


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
