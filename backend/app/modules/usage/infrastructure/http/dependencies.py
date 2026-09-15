from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database.session import AgentSessionDep
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.admin import require_platform_admin
from app.modules.usage.application.use_cases import (
    GetSystemUsageUseCase,
    GetUsageKpisUseCase,
    GetUserUsageUseCase,
    ListConversationUsageUseCase,
)
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.infrastructure.persistence.repositories import (
    SqlAlchemyUsageRepository,
)


def _settings() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(_settings)]


def get_usage_repository(session: AgentSessionDep, settings: SettingsDep) -> UsageRepository:
    return SqlAlchemyUsageRepository(session, reporting_timezone=settings.reporting_timezone)


UsageRepositoryDep = Annotated[UsageRepository, Depends(get_usage_repository)]


def get_user_usage_use_case(repository: UsageRepositoryDep) -> GetUserUsageUseCase:
    return GetUserUsageUseCase(repository)


def get_system_usage_use_case(repository: UsageRepositoryDep) -> GetSystemUsageUseCase:
    return GetSystemUsageUseCase(repository)


def get_usage_kpis_use_case(repository: UsageRepositoryDep) -> GetUsageKpisUseCase:
    return GetUsageKpisUseCase(repository)


def get_list_conversation_usage_use_case(
    repository: UsageRepositoryDep,
) -> ListConversationUsageUseCase:
    return ListConversationUsageUseCase(repository)


GetUserUsageUseCaseDep = Annotated[GetUserUsageUseCase, Depends(get_user_usage_use_case)]
GetSystemUsageUseCaseDep = Annotated[GetSystemUsageUseCase, Depends(get_system_usage_use_case)]
GetUsageKpisUseCaseDep = Annotated[GetUsageKpisUseCase, Depends(get_usage_kpis_use_case)]
ListConversationUsageUseCaseDep = Annotated[
    ListConversationUsageUseCase, Depends(get_list_conversation_usage_use_case)
]


# El consumo GLOBAL cruza empresas: quién preguntó y cuánto costó, de toda la
# instalación. Por eso pide administrador de la instalación y no de una base:
# el administrador del ERP del cliente A no tiene por qué ver el uso del
# cliente B. `require_platform_admin` deja pasar igual cuando hay una sola
# base registrada, que es el caso de la app de escritorio.
AdminUserDep = Annotated[AuthenticatedUser, Depends(require_platform_admin)]
