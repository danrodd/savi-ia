"""Formato de error de la API: `{"errorCode", "message"}` (mismo que el backend de SAVI)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.errors import DomainError

# Código de dominio -> estado HTTP. Lo que no figura aquí responde 400.
_DOMAIN_STATUS: dict[str, int] = {
    "enrollment_token_invalid": 404,
    "client_suspended": 403,
    "instance_unauthorized": 401,
    "instance_revoked": 401,
}


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


def _response(
    status_code: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"errorCode": code, "message": message},
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _response(exc.status_code, exc.code, exc.message, exc.headers)

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        status = _DOMAIN_STATUS.get(exc.code, 400)
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
        return _response(status, exc.code, exc.message, headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Solo las rutas de los campos: el mensaje de Pydantic puede repetir valores (tokens).
        fields = sorted({".".join(str(p) for p in e["loc"][1:]) or "body" for e in exc.errors()})
        return _response(
            422, "validation_error", "La solicitud no cumple el contrato: " + ", ".join(fields)
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _response(exc.status_code, code, str(exc.detail))
