"""Endpoints HTTP del módulo auth.

- POST /auth/login    → {access, refresh, user} o el desafío del segundo factor
- POST /auth/mfa/setup, /auth/mfa/setup/confirm, /auth/mfa/verify → segundo factor (TOTP)
- POST /auth/refresh  → rota tokens y devuelve nuevos
- POST /auth/logout   → revoca el refresh recibido (idempotente)
- GET  /auth/me       → devuelve el usuario del access token actual
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Request, status

from app.modules.auth.application.mfa import MfaChallengeRequired
from app.modules.auth.application.requests import (
    LoginRequest,
    MfaSetupRequest,
    MfaVerifyRequest,
    RefreshRequest,
)
from app.modules.auth.application.responses import (
    AuthenticatedUserResponse,
    BootstrapResponse,
    InstallationPolicyResponse,
    MfaChallengeResponse,
    MfaSetupResponse,
    ModulesVersionResponse,
    SessionDatabaseResponse,
    TokenResponse,
)
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.exceptions import (
    InvalidCredentialsError,
    InvalidMfaCodeError,
    InvalidTokenError,
    UserDisabledError,
)
from app.modules.auth.infrastructure.http.dependencies import (
    CurrentUserDep,
    LoginUseCaseDep,
    LogoutUseCaseDep,
    MfaServiceDep,
    RefreshUseCaseDep,
    SettingsDep,
    TokenServiceDep,
)
from app.modules.erp_databases.infrastructure.http.dependencies import (
    ErpDatabaseRepositoryDep,
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


async def _session_database(
    user: AuthenticatedUser, repository: ErpDatabaseRepositoryDep
) -> SessionDatabaseResponse | None:
    """Código y nombre de la base de login, para que la interfaz diga en
    qué cliente está la sesión."""
    if user.erp_database_id is None:
        return None
    database = await repository.get_by_id(user.erp_database_id)
    if database is None:
        return None
    return SessionDatabaseResponse(id=database.id, code=database.code, name=database.name)


@router.post("/login", response_model=TokenResponse | MfaChallengeResponse)
async def login(
    http_request: Request,
    request: LoginRequest,
    use_case: LoginUseCaseDep,
    settings: SettingsDep,
    databases: ErpDatabaseRepositoryDep,
) -> TokenResponse | MfaChallengeResponse:
    # El límite va ANTES del caso de uso: si corriera después, cada intento
    # rechazado igual pagaría el viaje al ERP y el hash, que es justo el
    # trabajo que un ataque de fuerza bruta busca hacernos gastar.
    enforce_login_limits(http_request, settings, request.login)
    try:
        tokens, user = await use_case.execute(request.login, request.password)
    except MfaChallengeRequired as pending:
        # La contraseña estaba bien, pero NO se limpia el contador de fallos: si lo hiciera,
        # quien conoce la contraseña podría adivinar el código intercalando logins
        # correctos que lo reinician. Se limpia recién cuando el código es correcto.
        challenge = pending.challenge
        return MfaChallengeResponse(
            status="mfa_setup_required" if challenge.setup_required else "mfa_required",
            mfa_token=challenge.token,
            expires_in=challenge.expires_in,
        )
    except (InvalidCredentialsError, UserDisabledError):
        record_login_failure(settings, request.login)
        raise
    record_login_success(settings, request.login)
    return TokenResponse.from_domain(tokens, user, await _session_database(user, databases))


def _mfa_limit_key(claims_login: str, database_id: UUID) -> str:
    """Clave de límite del segundo factor: por usuario real, no por lo que se escribió."""
    return f"mfa:{database_id}:{claims_login}"


@router.post("/mfa/setup", response_model=MfaSetupResponse)
async def mfa_setup(
    http_request: Request,
    request: MfaSetupRequest,
    service: MfaServiceDep,
    tokens: TokenServiceDep,
    settings: SettingsDep,
    databases: ErpDatabaseRepositoryDep,
) -> MfaSetupResponse:
    """Genera el secreto (queda pendiente hasta confirmar un código) y devuelve lo que
    muestra la pantalla: la URI del QR y la clave para cargar a mano."""
    claims = tokens.decode(request.mfa_token)
    enforce_login_limits(
        http_request, settings, _mfa_limit_key(claims.login, claims.erp_database_id)
    )
    database = await databases.get_by_id(claims.erp_database_id)
    label = f"{claims.login}@{database.code}" if database is not None else claims.login
    setup = await service.begin_setup(request.mfa_token, account_label=label)
    return MfaSetupResponse(secret=setup.secret, otpauth_uri=setup.otpauth_uri)


@router.post("/mfa/setup/confirm", response_model=TokenResponse)
async def mfa_setup_confirm(
    http_request: Request,
    request: MfaVerifyRequest,
    service: MfaServiceDep,
    tokens: TokenServiceDep,
    use_case: LoginUseCaseDep,
    settings: SettingsDep,
    databases: ErpDatabaseRepositoryDep,
) -> TokenResponse:
    return await _complete_mfa(
        http_request, request, service.confirm_setup, tokens, use_case, settings, databases
    )


@router.post("/mfa/verify", response_model=TokenResponse)
async def mfa_verify(
    http_request: Request,
    request: MfaVerifyRequest,
    service: MfaServiceDep,
    tokens: TokenServiceDep,
    use_case: LoginUseCaseDep,
    settings: SettingsDep,
    databases: ErpDatabaseRepositoryDep,
) -> TokenResponse:
    return await _complete_mfa(
        http_request, request, service.verify, tokens, use_case, settings, databases
    )


async def _complete_mfa(
    http_request: Request,
    request: MfaVerifyRequest,
    check_code: Callable[[str, str], Awaitable[AuthenticatedUser]],
    tokens: TokenServiceDep,
    use_case: LoginUseCaseDep,
    settings: SettingsDep,
    databases: ErpDatabaseRepositoryDep,
) -> TokenResponse:
    """Valida el código y recién entonces abre la sesión."""
    claims = tokens.decode(request.mfa_token)
    key = _mfa_limit_key(claims.login, claims.erp_database_id)
    # Mismo límite y bloqueo que el login: 6 dígitos se adivinan sin freno.
    enforce_login_limits(http_request, settings, key)
    try:
        user = await check_code(request.mfa_token, request.code)
    except (InvalidMfaCodeError, InvalidTokenError):
        record_login_failure(settings, key)
        raise
    record_login_success(settings, key)
    pair, user = await use_case.issue_session(user)
    return TokenResponse.from_domain(pair, user, await _session_database(user, databases))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    http_request: Request,
    request: RefreshRequest,
    use_case: RefreshUseCaseDep,
    settings: SettingsDep,
    databases: ErpDatabaseRepositoryDep,
) -> TokenResponse:
    # Por IP: acá todavía no hay usuario resuelto, y sin límite el refresh es
    # un oráculo gratis para probar tokens.
    enforce_refresh_limits(http_request, settings)
    tokens, user = await use_case.execute(request.refresh_token)
    return TokenResponse.from_domain(tokens, user, await _session_database(user, databases))


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
async def me(
    user: CurrentUserDep, databases: ErpDatabaseRepositoryDep
) -> AuthenticatedUserResponse:
    """Devuelve el usuario del access token actual. Lo usa el frontend
    para hidratar la sesión al recargar la página."""
    return AuthenticatedUserResponse.from_domain(user, await _session_database(user, databases))


@router.get("/me/policy", response_model=InstallationPolicyResponse)
async def installation_policy(_: CurrentUserDep) -> InstallationPolicyResponse:
    """Si SEO Group dejó esta instalación solo con el chat. La interfaz lo usa para ocultar
    Administración (el API igual lo rechaza: esto solo evita mostrar lo que no funciona)."""
    from app.modules.auth.infrastructure.http.admin import config_is_locked

    return InstallationPolicyResponse(config_locked=await config_is_locked())


@router.get("/me/bootstrap", response_model=BootstrapResponse)
async def bootstrap(
    user: CurrentUserDep,
    use_case: ResolveModulesForDatabaseUseCaseDep,
    databases: ErpDatabaseRepositoryDep,
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
    return BootstrapResponse.from_database_access(
        user, access, await _session_database(user, databases)
    )


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
