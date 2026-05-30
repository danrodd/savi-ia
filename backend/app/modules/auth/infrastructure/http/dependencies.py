"""DI del módulo auth + dependency `get_current_user` para proteger rutas."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import get_agent_sessionmaker
from app.infrastructure.database.pool import get_erp_engine
from app.modules.auth.application.use_cases import (
    LoginUseCase,
    LogoutUseCase,
    RefreshTokensUseCase,
    ResolveUserFromAccessTokenUseCase,
)
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.exceptions import InvalidTokenError
from app.modules.auth.domain.interfaces import (
    PasswordHasher,
    RefreshTokenRepository,
    TokenService,
    UserRepository,
)
from app.modules.auth.infrastructure.persistence import (
    ErpUserRepository,
    SqlAlchemyRefreshTokenRepository,
)
from app.modules.auth.infrastructure.security import JwtTokenService, Md5PasswordHasher


def _settings() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(_settings)]


def get_token_service(settings: SettingsDep) -> TokenService:
    return JwtTokenService(settings)


TokenServiceDep = Annotated[TokenService, Depends(get_token_service)]


def get_password_hasher() -> PasswordHasher:
    return Md5PasswordHasher()


PasswordHasherDep = Annotated[PasswordHasher, Depends(get_password_hasher)]


def get_user_repository() -> UserRepository:
    return ErpUserRepository(get_erp_engine())


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_refresh_token_repository() -> RefreshTokenRepository:
    return SqlAlchemyRefreshTokenRepository(get_agent_sessionmaker())


RefreshTokenRepositoryDep = Annotated[
    RefreshTokenRepository, Depends(get_refresh_token_repository)
]


def get_login_use_case(
    users: UserRepositoryDep,
    refresh: RefreshTokenRepositoryDep,
    hasher: PasswordHasherDep,
    tokens: TokenServiceDep,
) -> LoginUseCase:
    return LoginUseCase(users, refresh, hasher, tokens)


def get_refresh_use_case(
    users: UserRepositoryDep,
    refresh: RefreshTokenRepositoryDep,
    tokens: TokenServiceDep,
) -> RefreshTokensUseCase:
    return RefreshTokensUseCase(users, refresh, tokens)


def get_logout_use_case(
    refresh: RefreshTokenRepositoryDep,
    tokens: TokenServiceDep,
) -> LogoutUseCase:
    return LogoutUseCase(refresh, tokens)


def get_resolve_user_use_case(
    tokens: TokenServiceDep,
) -> ResolveUserFromAccessTokenUseCase:
    return ResolveUserFromAccessTokenUseCase(tokens)


LoginUseCaseDep = Annotated[LoginUseCase, Depends(get_login_use_case)]
RefreshUseCaseDep = Annotated[RefreshTokensUseCase, Depends(get_refresh_use_case)]
LogoutUseCaseDep = Annotated[LogoutUseCase, Depends(get_logout_use_case)]
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
