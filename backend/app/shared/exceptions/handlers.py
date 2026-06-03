from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.modules.auth.domain.exceptions import (
    AuthError,
    ModuleAccessDeniedError,
    UserDisabledError,
)
from app.shared.exceptions.base import (
    DomainError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ModuleAccessDeniedError)
    async def _module_access_denied(
        _: Request, exc: ModuleAccessDeniedError
    ) -> JSONResponse:
        # Shape estructurado: el frontend usa `errorCode` para detectar
        # esto y recargar el bootstrap (caché de módulos stale).
        return JSONResponse(
            status_code=403,
            content={
                "errorCode": "module_access_denied",
                "detail": str(exc),
                "required_module": exc.required_module,
            },
        )

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ForbiddenError)
    async def _forbidden(_: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(UserDisabledError)
    async def _user_disabled(_: Request, exc: UserDisabledError) -> JSONResponse:
        # Más específico que AuthError → registramos antes para que
        # el dispatch lo capture primero.
        return JSONResponse(status_code=403, content={"detail": exc.message})

    @app.exception_handler(AuthError)
    async def _auth(_: Request, exc: AuthError) -> JSONResponse:
        # 401 con header `WWW-Authenticate` siguiendo el estándar OAuth2,
        # así el frontend puede distinguir auth vs otros errores sin
        # parsear el body.
        return JSONResponse(
            status_code=401,
            content={"detail": exc.message},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
