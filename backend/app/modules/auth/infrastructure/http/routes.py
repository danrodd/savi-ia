"""Endpoints HTTP del módulo auth.

- POST /auth/login    → {access, refresh, user}
- POST /auth/refresh  → rota tokens y devuelve nuevos
- POST /auth/logout   → revoca el refresh recibido (idempotente)
- GET  /auth/me       → devuelve el usuario del access token actual
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status

from app.modules.auth.application.requests import LoginRequest, RefreshRequest
from app.modules.auth.application.responses import (
    AuthenticatedUserResponse,
    BootstrapResponse,
    ModulesVersionResponse,
    TokenResponse,
)
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.exceptions import InvalidCredentialsError, UserDisabledError
from app.modules.auth.infrastructure.http.dependencies import (
    CurrentUserDep,
    LoginUseCaseDep,
    LogoutUseCaseDep,
    RefreshUseCaseDep,
    SettingsDep,
)
from app.modules.erp_databases.infrastructure.http.dependencies import (
    ResolveModulesForDatabaseUseCaseDep,
)
from app.shared.rate_limit import (
    enforce_login_limits,
    enforce_refresh_limits,
    record_login_failure,
    record_login_success,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_database(user: AuthenticatedUser) -> UUID:
    """La base del usuario. Nunca es `None`: el token no decodifica sin ella."""
    assert user.erp_database_id is not None  # noqa: S101
    return user.erp_database_id


@router.post("/login", response_model=TokenResponse)
async def login(
    http_request: Request,
    request: LoginRequest,
    use_case: LoginUseCaseDep,
    settings: SettingsDep,
) -> TokenResponse:
    # El límite va ANTES del caso de uso: si corriera después, cada intento
    # rechazado igual pagaría el viaje al ERP y el hash, que es justo el
    # trabajo que un ataque de fuerza bruta busca hacernos gastar.
    enforce_login_limits(http_request, settings, request.login)
    try:
        tokens, user = await use_case.execute(request.login, request.password)
    except (InvalidCredentialsError, UserDisabledError):
        record_login_failure(settings, request.login)
        raise
    record_login_success(settings, request.login)
    return TokenResponse.from_domain(tokens, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    http_request: Request,
    request: RefreshRequest,
    use_case: RefreshUseCaseDep,
    settings: SettingsDep,
) -> TokenResponse:
    # Por IP: acá todavía no hay usuario resuelto, y sin límite el refresh es
    # un oráculo gratis para probar tokens.
    enforce_refresh_limits(http_request, settings)
    tokens, user = await use_case.execute(request.refresh_token)
    return TokenResponse.from_domain(tokens, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: RefreshRequest,
    use_case: LogoutUseCaseDep,
) -> None:
    """Recibe el `refresh_token` (no el access) para revocarlo.

    Idempotente: si el token ya estaba revocado o es inválido, devuelve
    204 igual. El access lo descarta el cliente — no necesita reportarlo.
    """
    await use_case.execute(request.refresh_token)


@router.get("/me", response_model=AuthenticatedUserResponse)
async def me(user: CurrentUserDep) -> AuthenticatedUserResponse:
    """Devuelve el usuario del access token actual. Lo usa el frontend
    para hidratar la sesión al recargar la página."""
    return AuthenticatedUserResponse.from_domain(user)


@router.get("/me/bootstrap", response_model=BootstrapResponse)
async def bootstrap(
    user: CurrentUserDep,
    use_case: ResolveModulesForDatabaseUseCaseDep,
) -> BootstrapResponse:
    """Snapshot completo: identidad + módulos accesibles + version hash.

    El frontend lo llama tras el login y tras detectar cambios de
    versión via /me/modules-version. Es la fuente de verdad para la UI.

    Resuelve contra **la base del usuario**, no contra la base por defecto.
    Antes usaba un resolver atado a la default: un usuario de otra base
    recibía los módulos del usuario con el mismo `idUsuario` allá, que es
    exactamente el cruce de identidades que el multi-BD viene a evitar.
    """
    access = await use_case.execute(user.login, _require_database(user))
    return BootstrapResponse.from_database_access(user, access)


@router.get("/me/modules-version", response_model=ModulesVersionResponse)
async def modules_version(
    user: CurrentUserDep,
    use_case: ResolveModulesForDatabaseUseCaseDep,
) -> ModulesVersionResponse:
    """Hash de versión actual de los módulos del usuario.

    Endpoint barato para polling — recalcula sobre el ERP pero solo
    devuelve el hash. El cliente lo compara contra el cacheado y, si
    cambió, recarga el bootstrap completo.
    """
    access = await use_case.execute(user.login, _require_database(user))
    return ModulesVersionResponse.from_database_access(access)
