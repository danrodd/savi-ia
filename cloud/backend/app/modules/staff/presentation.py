"""Rutas de autenticación del staff: `/console/auth/*` (§2.2) y `/console/api/me`."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import RateLimiters, transaction
from app.modules.staff.application import (
    AuthFailure,
    BeginMfaSetupUseCase,
    ConfirmMfaSetupUseCase,
    LoginUseCase,
    LogoutUseCase,
    Principal,
    RefreshSessionUseCase,
    TokenPair,
    VerifyMfaUseCase,
)
from app.modules.staff.dependencies import (
    RequirePermission,
    build_auth_deps,
    request_context,
)
from app.modules.staff.domain import Permission, StaffUser, permissions_of
from app.modules.staff.security import REFRESH_TTL
from app.shared.http_errors import ApiError

REFRESH_COOKIE = "savi_console_refresh"
REFRESH_COOKIE_PATH = "/console/auth"

_FAILURE_STATUS = {
    "invalid_credentials": 401,
    "invalid_mfa_code": 401,
    "invalid_session_token": 401,
    "weak_password": 422,
}

auth_router = APIRouter(prefix="/console/auth", tags=["console-auth"])
console_router = APIRouter(prefix="/console/api", tags=["console"])


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(_Body):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    status: Literal["mfa_required", "mfa_setup_required"]
    token: str
    must_change_password: bool = False


class MfaRequest(_Body):
    mfa_token: str = Field(min_length=1, max_length=2048)
    code: str = Field(min_length=1, max_length=16)


class MfaSetupRequest(_Body):
    setup_token: str = Field(min_length=1, max_length=2048)


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaSetupConfirmRequest(_Body):
    setup_token: str = Field(min_length=1, max_length=2048)
    code: str = Field(min_length=1, max_length=16)
    new_password: str | None = Field(default=None, max_length=256)


class StaffUserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    permissions: list[str]

    @classmethod
    def of(cls, user: StaffUser) -> StaffUserResponse:
        return cls(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            permissions=[p.value for p in permissions_of(user.role)],
        )


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    must_change_password: bool
    user: StaffUserResponse


def _limiters(request: Request) -> RateLimiters:
    limiters: RateLimiters = request.app.state.limiters
    return limiters


def _enforce_auth_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    retry_after = _limiters(request).console_auth.hit(ip)
    if retry_after is not None:
        raise ApiError(
            429,
            "too_many_requests",
            "Demasiados intentos; espere unos minutos.",
            {"Retry-After": str(retry_after)},
        )


def _fail(failure: AuthFailure) -> ApiError:
    return ApiError(_FAILURE_STATUS.get(failure.code, 400), failure.code, failure.message)


def _set_refresh_cookie(request: Request, response: Response, token: str) -> None:
    secure: bool = request.app.state.settings.console_cookie_secure
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=int(REFRESH_TTL.total_seconds()),
        httponly=True,
        secure=secure,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )


def _token_response(request: Request, response: Response, pair: TokenPair) -> TokenResponse:
    _set_refresh_cookie(request, response, pair.refresh_token)
    return TokenResponse(
        access_token=pair.access_token,
        expires_in=pair.expires_in,
        must_change_password=pair.must_change_password,
        user=StaffUserResponse.of(pair.user),
    )


@auth_router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    _enforce_auth_limit(request)
    async with transaction(request) as session:
        result = await LoginUseCase(build_auth_deps(request, session)).execute(
            body.email, body.password, request_context(request)
        )
    if isinstance(result, AuthFailure):
        raise _fail(result)
    return LoginResponse(
        status=result.next_step,
        token=result.token,
        must_change_password=result.must_change_password,
    )


@auth_router.post("/mfa", response_model=TokenResponse)
async def verify_mfa(body: MfaRequest, request: Request, response: Response) -> TokenResponse:
    _enforce_auth_limit(request)
    async with transaction(request) as session:
        result = await VerifyMfaUseCase(build_auth_deps(request, session)).execute(
            body.mfa_token, body.code, request_context(request)
        )
    if isinstance(result, AuthFailure):
        raise _fail(result)
    return _token_response(request, response, result)


@auth_router.post("/mfa/setup", response_model=MfaSetupResponse)
async def begin_mfa_setup(body: MfaSetupRequest, request: Request) -> MfaSetupResponse:
    _enforce_auth_limit(request)
    async with transaction(request) as session:
        setup = await BeginMfaSetupUseCase(build_auth_deps(request, session)).execute(
            body.setup_token
        )
    return MfaSetupResponse(secret=setup.secret, otpauth_uri=setup.otpauth_uri)


@auth_router.post("/mfa/setup/confirm", response_model=TokenResponse)
async def confirm_mfa_setup(
    body: MfaSetupConfirmRequest, request: Request, response: Response
) -> TokenResponse:
    _enforce_auth_limit(request)
    async with transaction(request) as session:
        result = await ConfirmMfaSetupUseCase(build_auth_deps(request, session)).execute(
            body.setup_token, body.code, body.new_password, request_context(request)
        )
    if isinstance(result, AuthFailure):
        raise _fail(result)
    return _token_response(request, response, result)


def _failure_response(failure: AuthFailure) -> JSONResponse:
    """Error que además borra la cookie (un `raise` perdería los cambios de `Response`)."""
    error = JSONResponse(
        status_code=_FAILURE_STATUS.get(failure.code, 400),
        content={"errorCode": failure.code, "message": failure.message},
    )
    error.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    return error


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response) -> TokenResponse | JSONResponse:
    _enforce_auth_limit(request)
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        return _failure_response(
            AuthFailure("invalid_session_token", "La sesión venció; inicie sesión de nuevo.")
        )
    async with transaction(request) as session:
        result = await RefreshSessionUseCase(build_auth_deps(request, session)).execute(
            token, request_context(request)
        )
    if isinstance(result, AuthFailure):
        return _failure_response(result)
    return _token_response(request, response, result)


@auth_router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    async with transaction(request) as session:
        await LogoutUseCase(build_auth_deps(request, session)).execute(
            request.cookies.get(REFRESH_COOKIE), request_context(request)
        )
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


@console_router.get("/me", response_model=StaffUserResponse)
async def me(
    principal: Principal = Depends(RequirePermission(Permission.OVERVIEW_READ)),
) -> StaffUserResponse:
    return StaffUserResponse.of(principal.user)
