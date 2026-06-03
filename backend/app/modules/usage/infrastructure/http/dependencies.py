from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database.session import AgentSessionDep
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http import CurrentUserDep
from app.modules.usage.application.use_cases import (
    GetSystemUsageUseCase,
    GetUserUsageUseCase,
)
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.infrastructure.persistence.repositories import (
    SqlAlchemyUsageRepository,
)
from app.shared.exceptions import ForbiddenError


def _settings() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(_settings)]


def get_usage_repository(
    session: AgentSessionDep, settings: SettingsDep
) -> UsageRepository:
    return SqlAlchemyUsageRepository(
        session, reporting_timezone=settings.reporting_timezone
    )


UsageRepositoryDep = Annotated[UsageRepository, Depends(get_usage_repository)]


def get_user_usage_use_case(repository: UsageRepositoryDep) -> GetUserUsageUseCase:
    return GetUserUsageUseCase(repository)


def get_system_usage_use_case(repository: UsageRepositoryDep) -> GetSystemUsageUseCase:
    return GetSystemUsageUseCase(repository)


GetUserUsageUseCaseDep = Annotated[
    GetUserUsageUseCase, Depends(get_user_usage_use_case)
]
GetSystemUsageUseCaseDep = Annotated[
    GetSystemUsageUseCase, Depends(get_system_usage_use_case)
]


def require_admin(user: CurrentUserDep) -> AuthenticatedUser:
    """Gate de la vista administrativa: solo usuarios admin del ERP.

    Levanta `ForbiddenError` (→ 403) si el usuario autenticado no es admin.
    """
    if not user.is_admin:
        raise ForbiddenError("Se requiere rol administrador para ver el consumo global")
    return user


AdminUserDep = Annotated[AuthenticatedUser, Depends(require_admin)]
