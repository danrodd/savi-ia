"""DI del módulo `erp_databases`."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import get_agent_sessionmaker
from app.modules.auth.application.use_cases import ResolveModulesForDatabaseUseCase
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.persistence import (
    ErpPermissionRepositoryFactory,
    ErpSeoPlanRepositoryFactory,
    ErpUserRepositoryFactory,
)
from app.modules.erp_databases.application.use_cases import (
    ExportImportErpDatabasesUseCase,
    ListAvailableDatabasesUseCase,
    ManageErpDatabasesUseCase,
)
from app.modules.erp_databases.domain.interfaces import (
    ConnectionTester,
    DatabaseAccessPolicy,
    ErpDatabaseRepository,
    UnrestrictedDatabases,
)
from app.modules.erp_databases.infrastructure import get_connection_provider
from app.modules.erp_databases.infrastructure.engine_registry import (
    get_engine_registry,
)
from app.modules.erp_databases.infrastructure.persistence import (
    SqlAlchemyErpDatabaseRepository,
)
from app.modules.erp_databases.infrastructure.postgres_connection_tester import (
    PostgresConnectionTester,
)
from app.shared.security import FernetCredentialCipher

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_erp_database_repository(settings: SettingsDep) -> ErpDatabaseRepository:
    cipher = FernetCredentialCipher(
        settings.erp_credentials_key,
        old_keys=[settings.erp_credentials_key_old],
    )
    return SqlAlchemyErpDatabaseRepository(get_agent_sessionmaker(), cipher)


ErpDatabaseRepositoryDep = Annotated[
    ErpDatabaseRepository, Depends(get_erp_database_repository)
]


def get_connection_tester() -> ConnectionTester:
    return PostgresConnectionTester()


ConnectionTesterDep = Annotated[ConnectionTester, Depends(get_connection_tester)]


def get_manage_use_case(
    repository: ErpDatabaseRepositoryDep,
    tester: ConnectionTesterDep,
) -> ManageErpDatabasesUseCase:
    return ManageErpDatabasesUseCase(repository, tester, get_engine_registry())


ManageErpDatabasesUseCaseDep = Annotated[
    ManageErpDatabasesUseCase, Depends(get_manage_use_case)
]


def get_export_import_use_case(
    repository: ErpDatabaseRepositoryDep,
    manager: ManageErpDatabasesUseCaseDep,
) -> ExportImportErpDatabasesUseCase:
    return ExportImportErpDatabasesUseCase(repository, manager)


ExportImportErpDatabasesUseCaseDep = Annotated[
    ExportImportErpDatabasesUseCase, Depends(get_export_import_use_case)
]


def get_resolve_modules_for_database_use_case() -> ResolveModulesForDatabaseUseCase:
    """Resolver D3: permisos en la base que se consulta, por `codigo`.

    Se arma acá y no vía DI de FastAPI porque también lo usan flujos sin
    request (el turno del chat clausura sus dependencias).
    """
    provider = get_connection_provider()
    return ResolveModulesForDatabaseUseCase(
        ErpUserRepositoryFactory(
            get_erp_database_repository(get_settings()),
            get_engine_registry(),
            provider,
        ),
        ErpPermissionRepositoryFactory(provider),
        ErpSeoPlanRepositoryFactory(provider),
        is_platform_admin=_is_platform_admin,
    )


async def _is_platform_admin(user: AuthenticatedUser) -> bool:
    """El administrador de la instalación entra a todas las bases. Import
    adentro: `auth.infrastructure.http.admin` importa de este módulo."""
    from app.modules.auth.infrastructure.http.admin import is_platform_admin

    return await is_platform_admin(user, get_settings())


def get_database_access_policy() -> DatabaseAccessPolicy:
    """Bases que SEO Group asignó a cada persona (Cloud). Import adentro: `cloud_link`
    importa modelos de otros módulos."""
    from app.modules.cloud_link.application.pseudonymizer import PseudonymizerProvider
    from app.modules.cloud_link.infrastructure.composition import get_cloud_link_services
    from app.modules.cloud_link.infrastructure.database_access_policy import (
        CloudDatabaseAccessPolicy,
    )

    try:
        services = get_cloud_link_services()
    except RuntimeError:
        return UnrestrictedDatabases()
    return CloudDatabaseAccessPolicy(
        services.repository, PseudonymizerProvider(services.repository)
    )


DatabaseAccessPolicyDep = Annotated[DatabaseAccessPolicy, Depends(get_database_access_policy)]


def get_list_available_use_case(
    repository: ErpDatabaseRepositoryDep,
    access_policy: DatabaseAccessPolicyDep,
) -> ListAvailableDatabasesUseCase:
    return ListAvailableDatabasesUseCase(
        repository, get_resolve_modules_for_database_use_case(), access_policy
    )


ListAvailableDatabasesUseCaseDep = Annotated[
    ListAvailableDatabasesUseCase, Depends(get_list_available_use_case)
]


ResolveModulesForDatabaseUseCaseDep = Annotated[
    ResolveModulesForDatabaseUseCase,
    Depends(get_resolve_modules_for_database_use_case),
]
