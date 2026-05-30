"""Endpoints HTTP del módulo auth.

- POST /auth/login    → {access, refresh, user}
- POST /auth/refresh  → rota tokens y devuelve nuevos
- POST /auth/logout   → revoca el refresh recibido (idempotente)
- GET  /auth/me       → devuelve el usuario del access token actual
"""
from __future__ import annotations

from fastapi import APIRouter, status

from app.modules.auth.application.requests import LoginRequest, RefreshRequest
from app.modules.auth.application.responses import (
    AuthenticatedUserResponse,
    TokenResponse,
)
from app.modules.auth.infrastructure.http.dependencies import (
    CurrentUserDep,
    LoginUseCaseDep,
    LogoutUseCaseDep,
    RefreshUseCaseDep,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    use_case: LoginUseCaseDep,
) -> TokenResponse:
    tokens, user = await use_case.execute(request.login, request.password)
    return TokenResponse.from_domain(tokens, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    use_case: RefreshUseCaseDep,
) -> TokenResponse:
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
