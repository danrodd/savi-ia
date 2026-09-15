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

    # Import local para no crear un ciclo: este módulo lo importa el
    # paquete `shared.exceptions`, y la excepción vive en un módulo que a
    # su vez depende de `shared.exceptions.base`.
    from app.modules.chat.domain.exceptions import LlmProviderUnavailableError
    from app.modules.erp_databases.domain.exceptions import (
        ErpDatabaseUnavailableError,
    )

    @app.exception_handler(LlmProviderUnavailableError)
    async def _llm_provider_unavailable(
        _: Request, exc: LlmProviderUnavailableError
    ) -> JSONResponse:
        # 409 como la base no disponible: el pedido es válido, lo que
        # falla es la configuración. El frontend usa el `errorCode` para
        # mandar al administrador a configurar la IA.
        return JSONResponse(
            status_code=409,
            content={"errorCode": "llm_provider_unavailable", "detail": exc.reason},
        )

    @app.exception_handler(ErpDatabaseUnavailableError)
    async def _erp_unavailable(
        _: Request, exc: ErpDatabaseUnavailableError
    ) -> JSONResponse:
        # 409 y no 404: la conversación y la base existen, lo que falla es
        # el estado (desactivada, eliminada o sin acceso). El frontend usa
        # el `errorCode` para mostrar el banner de solo lectura en lugar de
        # un error genérico.
        return JSONResponse(
            status_code=409,
            content={
                "errorCode": "erp_database_unavailable",
                "detail": exc.reason,
                "erp_database_id": exc.database_id,
            },
        )

    from app.modules.company_knowledge.domain.exceptions import (
        CompanyDocumentConflictError,
        CompanyDocumentFileTooLargeError,
        CompanyDocumentIndexLimitReachedError,
        DuplicateCompanyDocumentError,
        UnsupportedCompanyDocumentMediaTypeError,
    )

    @app.exception_handler(CompanyDocumentFileTooLargeError)
    async def _document_too_large(
        _: Request, exc: CompanyDocumentFileTooLargeError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={"errorCode": "file_too_large", "detail": str(exc), "limit_mb": exc.limit_mb},
        )

    @app.exception_handler(UnsupportedCompanyDocumentMediaTypeError)
    async def _document_media_type(
        _: Request, exc: UnsupportedCompanyDocumentMediaTypeError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=415,
            content={"errorCode": "unsupported_media_type", "detail": str(exc)},
        )

    @app.exception_handler(DuplicateCompanyDocumentError)
    async def _document_duplicate(_: Request, exc: DuplicateCompanyDocumentError) -> JSONResponse:
        # El frontend enlaza al documento existente en lugar de un error seco.
        return JSONResponse(
            status_code=409,
            content={
                "errorCode": "duplicate_document",
                "detail": str(exc),
                "existing_document_id": exc.existing_document_id,
                "existing_title": exc.existing_title,
            },
        )

    @app.exception_handler(CompanyDocumentIndexLimitReachedError)
    async def _document_index_limit(
        _: Request, exc: CompanyDocumentIndexLimitReachedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"errorCode": "index_limit_reached", "detail": str(exc), "limit": exc.limit},
        )

    @app.exception_handler(CompanyDocumentConflictError)
    async def _document_conflict(_: Request, exc: CompanyDocumentConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"errorCode": "document_conflict", "detail": str(exc)}
        )

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
