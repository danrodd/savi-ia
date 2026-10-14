"""DI del módulo auth + dependency `get_current_user` para proteger rutas."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Header

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import get_agent_sessionmaker
from app.modules.auth.application.mfa import MfaService
from app.modules.auth.application.use_cases import (
    LoginUseCase,
    LogoutUseCase,
    RefreshTokensUseCase,
    ResetMfaUseCase,
    ResolveUserFromAccessTokenUseCase,
)
from app.modules.auth.application.use_cases.resolve_modules_for_database import (
    ResolveModulesForDatabaseUseCase,
)
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.exceptions import (
    InvalidTokenError,
    ModuleAccessDeniedError,
)
from app.modules.auth.domain.interfaces import (
    PasswordHasher,
    RefreshTokenRepository,
    TokenService,
    TotpRepository,
    UserRepositoryFactory,
)
from app.modules.auth.domain.value_objects import ModuleCode
from app.modules.auth.infrastructure.persistence import (
    ErpUserRepositoryFactory,
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyTotpRepository,
)
from app.modules.auth.infrastructure.security import JwtTokenService, Md5PasswordHasher
from app.modules.erp_databases.infrastructure import (
    get_connection_provider,
    get_engine_registry,
)
from app.modules.erp_databases.infrastructure.persistence import (
    SqlAlchemyErpDatabaseRepository,
)
from app.shared.security import FernetCredentialCipher


def _settings() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(_settings)]


def get_token_service(settings: SettingsDep) -> TokenService:
    return JwtTokenService(settings)


TokenServiceDep = Annotated[TokenService, Depends(get_token_service)]


def get_password_hasher() -> PasswordHasher:
    return Md5PasswordHasher()


PasswordHasherDep = Annotated[PasswordHasher, Depends(get_password_hasher)]


def get_user_repository_factory() -> UserRepositoryFactory:
    """Fábrica de repositorios de usuarios, una por base de cliente.

    Login y refresh no pueden recibir un repositorio ya resuelto: cuál
    usar depende del login que llega en el request (`JPEREZ@NORTE`), y
    eso se sabe recién dentro del caso de uso.
    """
    cipher = FernetCredentialCipher(
        get_settings().erp_credentials_key,
        old_keys=[get_settings().erp_credentials_key_old],
    )
    databases = SqlAlchemyErpDatabaseRepository(get_agent_sessionmaker(), cipher)
    return ErpUserRepositoryFactory(databases, get_engine_registry(), get_connection_provider())


UserRepositoryFactoryDep = Annotated[UserRepositoryFactory, Depends(get_user_repository_factory)]


def get_refresh_token_repository() -> RefreshTokenRepository:
    return SqlAlchemyRefreshTokenRepository(get_agent_sessionmaker())


RefreshTokenRepositoryDep = Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)]


def get_totp_repository(settings: SettingsDep) -> TotpRepository:
    cipher = FernetCredentialCipher(
        settings.erp_credentials_key, old_keys=[settings.erp_credentials_key_old]
    )
    return SqlAlchemyTotpRepository(get_agent_sessionmaker(), cipher)


TotpRepositoryDep = Annotated[TotpRepository, Depends(get_totp_repository)]


def _mfa_required_for(settings: Settings) -> Callable[[AuthenticatedUser], bool]:
    """A quién le toca el segundo factor según `MFA_ENFORCEMENT`.

    `admins` cubre al administrador del ERP de su base y a los de `SAVI_ADMIN_LOGINS`: la
    misma definición de "administrador de SAVI" que usan las pantallas de Administración.
    """
    mode = settings.mfa_enforcement
    if mode == "off":
        return lambda _user: False
    if mode == "all":
        return lambda _user: True
    listed = settings.savi_admin_logins_set
    return lambda user: user.is_admin or user.login.strip().upper() in listed


def get_mfa_service(
    settings: SettingsDep, totp: TotpRepositoryDep, tokens: TokenServiceDep
) -> MfaService:
    return MfaService(
        totp_repository=totp,
        token_service=tokens,
        is_required=_mfa_required_for(settings),
        issuer=settings.mfa_issuer,
    )


MfaServiceDep = Annotated[MfaService, Depends(get_mfa_service)]


def get_login_use_case(
    users: UserRepositoryFactoryDep,
    refresh: RefreshTokenRepositoryDep,
    hasher: PasswordHasherDep,
    tokens: TokenServiceDep,
    mfa: MfaServiceDep,
) -> LoginUseCase:
    return LoginUseCase(users, refresh, hasher, tokens, mfa)


def get_refresh_use_case(
    users: UserRepositoryFactoryDep,
    refresh: RefreshTokenRepositoryDep,
    tokens: TokenServiceDep,
) -> RefreshTokensUseCase:
    return RefreshTokensUseCase(users, refresh, tokens)


def get_logout_use_case(
    refresh: RefreshTokenRepositoryDep,
    tokens: TokenServiceDep,
) -> LogoutUseCase:
    return LogoutUseCase(refresh, tokens)


class _ErpDatabaseLookup:
    """Adaptador: código de cliente -> id de base, sobre el repositorio de `erp_databases`."""

    def __init__(self, settings: Settings) -> None:
        cipher = FernetCredentialCipher(
            settings.erp_credentials_key, old_keys=[settings.erp_credentials_key_old]
        )
        self._repository = SqlAlchemyErpDatabaseRepository(get_agent_sessionmaker(), cipher)

    async def database_id_for(self, code: str | None):  # type: ignore[no-untyped-def]
        database = (
            await self._repository.get_default()
            if code is None
            else await self._repository.get_by_code(code.strip().upper())
        )
        return database.id if database is not None else None


def get_reset_mfa_use_case(
    settings: SettingsDep, totp: TotpRepositoryDep, refresh: RefreshTokenRepositoryDep
) -> ResetMfaUseCase:
    return ResetMfaUseCase(totp, refresh, _ErpDatabaseLookup(settings))


def get_resolve_user_use_case(
    tokens: TokenServiceDep,
) -> ResolveUserFromAccessTokenUseCase:
    return ResolveUserFromAccessTokenUseCase(tokens)


# Acá vivían `get_permission_repository`, `get_seo_plan_repository` y
# `get_resolve_user_modules_use_case`, todos atados a `get_erp_engine_for(None)`
# — es decir, a la base POR DEFECTO. Se eliminaron: un usuario de otra base
# recibía los permisos del usuario con el mismo `idUsuario` en la default.
#
# Quien necesite módulos usa `ResolveModulesForDatabaseUseCase`, que exige
# decir contra qué base resolver. Un resolver que elige la base en silencio
# es una trampa para el próximo endpoint que lo use.


LoginUseCaseDep = Annotated[LoginUseCase, Depends(get_login_use_case)]
RefreshUseCaseDep = Annotated[RefreshTokensUseCase, Depends(get_refresh_use_case)]
LogoutUseCaseDep = Annotated[LogoutUseCase, Depends(get_logout_use_case)]
ResetMfaUseCaseDep = Annotated[ResetMfaUseCase, Depends(get_reset_mfa_use_case)]
ResolveUserUseCaseDep = Annotated[
    ResolveUserFromAccessTokenUseCase, Depends(get_resolve_user_use_case)
]


_BEARER_PREFIX = "Bearer "


def get_current_user(
    resolver: ResolveUserUseCaseDep,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    """Dependency que protege rutas. Extrae el Bearer del header
    `Authorization` y resuelve el usuario. Levanta `InvalidTokenError`
    (mapeado a 401) si falta o es inválido.
    """
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        raise InvalidTokenError("Falta header Authorization Bearer")
    token = authorization[len(_BEARER_PREFIX) :].strip()
    if not token:
        raise InvalidTokenError("Token vacío")
    return resolver.execute(token)


CurrentUserDep = Annotated[AuthenticatedUser, Depends(get_current_user)]


def _resolve_modules_for_database() -> ResolveModulesForDatabaseUseCase:
    """Puente al proveedor que vive en `erp_databases`.

    El import va adentro y no arriba: `erp_databases` importa de `auth`, así
    que a nivel de módulo sería un ciclo. La CLASE sí se importa arriba —
    vive en la capa de aplicación de `auth`— para que la anotación del
    parámetro se resuelva sin trucos.
    """
    from app.modules.erp_databases.infrastructure.http.dependencies import (
        get_resolve_modules_for_database_use_case,
    )

    return get_resolve_modules_for_database_use_case()


def RequireModule(  # noqa: N802 — factory que produce dependencies; mantenemos PascalCase.
    code: ModuleCode,
) -> Callable[..., Awaitable[AuthenticatedUser]]:
    """Factory que produce una dependency FastAPI que exige acceso a un
    módulo del ERP.

    El access token solo trae identidad: para chequear módulos hay que
    resolverlos en BD (rápido — un par de queries triviales). Si querés
    proteger un endpoint:

        @router.get("/saldos")
        async def saldos(
            user: Annotated[AuthenticatedUser, Depends(RequireModule(ModuleCode.CONTABILIDAD))],
        ):
            ...

    Si el usuario no tiene el módulo, levanta `ModuleAccessDeniedError`
    que el handler global mapea a 403 con `errorCode: module_access_denied`.

    Resuelve contra **la base del usuario**. Antes usaba el resolver de la
    base por defecto: en una instalación con varias bases, el usuario 5 de la
    base B habría sido evaluado con los permisos del usuario 5 de la default.
    """

    async def _check(
        user: CurrentUserDep,
        resolver: Annotated[
            ResolveModulesForDatabaseUseCase, Depends(_resolve_modules_for_database)
        ],
    ) -> AuthenticatedUser:
        if user.erp_database_id is None:
            raise ModuleAccessDeniedError(code.value)
        access = await resolver.execute(user.login, user.erp_database_id)
        if not access.has_access or code not in access.modules:
            raise ModuleAccessDeniedError(code.value)
        return user

    return _check
