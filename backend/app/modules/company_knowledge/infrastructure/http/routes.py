"""Administración de documentos de la empresa.

Todo bajo `/admin/company-documents` con `SaviAdminDep`. Ningún response
incluye contenido del documento: solo metadatos y estado.
"""

from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Request, UploadFile, status

from app.infrastructure.config import Settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.auth.infrastructure.http.admin import SaviAdminDep, is_platform_admin
from app.modules.company_knowledge.application.mappers import CompanyDocumentMapper
from app.modules.company_knowledge.application.requests import (
    SearchTestRequest,
    UpdateAiReadingSettingsRequest,
    UpdateCompanyDocumentRequest,
)
from app.modules.company_knowledge.application.responses import (
    AiReadingSettingsResponse,
    CompanyDocumentResponse,
    CompanyDocumentUsageResponse,
    SearchTestResponse,
)
from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
)
from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentFileTooLargeError,
    CompanyDocumentInvalidError,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentVisibility,
)
from app.modules.company_knowledge.infrastructure.http.dependencies import (
    AiReadingSettingsUseCaseDep,
    DeleteUseCaseDep,
    GetUseCaseDep,
    ListUseCaseDep,
    ReadWithAiUseCaseDep,
    ReplaceUseCaseDep,
    ReprocessUseCaseDep,
    SearchTestUseCaseDep,
    SettingsDep,
    UpdateAiReadingSettingsUseCaseDep,
    UpdateUseCaseDep,
    UploadUseCaseDep,
    UsageUseCaseDep,
)
from app.shared.rate_limit import enforce_upload_limits

router = APIRouter(prefix="/admin/company-documents", tags=["company-documents"])

_READ_BLOCK = 1024 * 1024
# Margen para los campos del formulario y los separadores multipart.
_MULTIPART_OVERHEAD = 64 * 1024


def _response(document: CompanyDocument) -> CompanyDocumentResponse:
    return CompanyDocumentResponse.from_dto(CompanyDocumentMapper.to_dto(document))


def _reject_oversized_body(request: Request, limit_mb: int) -> None:
    """Rechaza por `Content-Length` antes de leer el cuerpo.

    Starlette parsea el multipart antes de llegar al endpoint, pero lo
    vuelca a un archivo temporal a partir de 1 MB: el costo de un archivo
    grande es disco, no memoria. Este chequeo corta los casos honestos sin
    siquiera eso; la lectura por bloques de `_read_limited` cubre un
    `Content-Length` ausente o falso.
    """
    declared = request.headers.get("content-length")
    limit = limit_mb * 1024 * 1024 + _MULTIPART_OVERHEAD
    if declared and declared.isdigit() and int(declared) > limit:
        raise CompanyDocumentFileTooLargeError(limit_mb)


async def _read_limited(file: UploadFile, limit_mb: int) -> bytes:
    limit = limit_mb * 1024 * 1024
    buffer = bytearray()
    while block := await file.read(_READ_BLOCK):
        buffer.extend(block)
        if len(buffer) > limit:
            raise CompanyDocumentFileTooLargeError(limit_mb)
    return bytes(buffer)


async def _scope_database(
    admin: AuthenticatedUser, settings: Settings, requested: UUID | None
) -> UUID | None:
    """Base a la que se acota la consulta.

    `None` solo para el administrador de la instalación: el de una empresa
    queda atado a la suya, aunque pida otra por query string.
    """
    if await is_platform_admin(admin, settings):
        return requested
    return admin.erp_database_id


def _parse_modules(values: list[str]) -> list[ModuleCode]:
    try:
        return [ModuleCode(value) for value in values]
    except ValueError as exc:
        raise CompanyDocumentInvalidError("Módulo del ERP no válido.") from exc


@router.post("", response_model=CompanyDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    use_case: UploadUseCaseDep,
    settings: SettingsDep,
    admin: SaviAdminDep,
    file: UploadFile = File(...),
    visibility: DocumentVisibility = Form(...),
    title: str | None = Form(default=None, max_length=200),
    modules: list[str] = Form(default_factory=list),
    all_databases: bool = Form(default=True),
    database_ids: list[UUID] = Form(default_factory=list),
) -> CompanyDocumentResponse:
    # Antes de leer el cuerpo: cada subida encola procesamiento (embeddings),
    # que es el trabajo caro. Con el usuario ya inyectado, sin resolver la
    # autenticación de nuevo.
    enforce_upload_limits(settings, admin)
    limit_mb = settings.company_docs_max_file_mb
    _reject_oversized_body(request, limit_mb)
    content = await _read_limited(file, limit_mb)
    assert admin.erp_database_id is not None  # noqa: S101 — el token no decodifica sin base
    document = await use_case.execute(
        filename=file.filename or "documento",
        content=content,
        title=title,
        visibility=visibility,
        modules=_parse_modules(modules),
        all_databases=all_databases,
        database_ids=database_ids,
        uploaded_by_login=admin.login,
        uploaded_by_database_id=admin.erp_database_id,
        uploaded_by_user_id=admin.id,
    )
    return _response(document)


@router.get("", response_model=list[CompanyDocumentResponse])
async def list_documents(
    use_case: ListUseCaseDep,
    admin: SaviAdminDep,
    settings: SettingsDep,
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    visibility: DocumentVisibility | None = Query(default=None),
    module: ModuleCode | None = Query(default=None),
    database_id: UUID | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[CompanyDocumentResponse]:
    # Un administrador de EMPRESA ve solo los documentos que alcanzan a su
    # base; uno de la instalación los ve todos. Cambiar solo el guard no
    # alcanzaba: la lista devolvía los documentos de todas las empresas.
    documents = await use_case.execute(
        status=status_filter,
        visibility=visibility,
        module=module,
        database_id=await _scope_database(admin, settings, database_id),
        query=q,
        limit=limit,
        offset=offset,
    )
    return [_response(document) for document in documents]


@router.get("/usage", response_model=CompanyDocumentUsageResponse)
async def usage(use_case: UsageUseCaseDep, _admin: SaviAdminDep) -> CompanyDocumentUsageResponse:
    return CompanyDocumentUsageResponse.from_dto(await use_case.execute())


@router.get("/ai-reading", response_model=AiReadingSettingsResponse)
async def get_ai_reading_settings(
    use_case: AiReadingSettingsUseCaseDep, _admin: SaviAdminDep
) -> AiReadingSettingsResponse:
    """Interruptor de la lectura de PDF con IA, proveedor, modelo y costo estimado."""
    return AiReadingSettingsResponse.from_status(await use_case.execute())


@router.put("/ai-reading", response_model=AiReadingSettingsResponse)
async def update_ai_reading_settings(
    request: UpdateAiReadingSettingsRequest,
    use_case: UpdateAiReadingSettingsUseCaseDep,
    admin: SaviAdminDep,
) -> AiReadingSettingsResponse:
    """Activa o apaga la lectura con IA. Aplica a lo que se procese después."""
    reading = await use_case.execute(
        enabled=request.ai_reading_enabled, updated_by_login=admin.login
    )
    return AiReadingSettingsResponse.from_status(reading)


@router.post("/search-test", response_model=SearchTestResponse)
async def search_test(
    request: SearchTestRequest, use_case: SearchTestUseCaseDep, admin: SaviAdminDep
) -> SearchTestResponse:
    """Prueba la búsqueda en una base, opcionalmente como otro usuario.

    Pasa por el mismo índice y la misma política que el chat. Devuelve además
    los documentos que la política excluyó y por qué: verificar permisos es
    el propósito de esta pantalla.
    """
    result = await use_case.execute(
        query=request.query,
        erp_database_id=request.erp_database_id,
        login=request.as_login or admin.login,
        admin_login=admin.login,
    )
    return SearchTestResponse.from_result(result)


@router.get("/{document_id}", response_model=CompanyDocumentResponse)
async def get_document(
    document_id: UUID, use_case: GetUseCaseDep, _admin: SaviAdminDep
) -> CompanyDocumentResponse:
    return _response(await use_case.execute(document_id))


@router.patch("/{document_id}", response_model=CompanyDocumentResponse)
async def update_document(
    document_id: UUID,
    request: UpdateCompanyDocumentRequest,
    use_case: UpdateUseCaseDep,
    _admin: SaviAdminDep,
) -> CompanyDocumentResponse:
    """Edita título y permisos. No reprocesa: aplica en la siguiente pregunta."""
    document = await use_case.execute(
        document_id,
        title=request.title,
        visibility=request.visibility,
        modules=request.modules,
        all_databases=request.all_databases,
        database_ids=request.database_ids,
    )
    return _response(document)


@router.post("/{document_id}/replace", response_model=CompanyDocumentResponse)
async def replace_document(
    document_id: UUID,
    request: Request,
    use_case: ReplaceUseCaseDep,
    settings: SettingsDep,
    admin: SaviAdminDep,
    file: UploadFile = File(...),
) -> CompanyDocumentResponse:
    # Reemplazar también encola procesamiento: cuenta para el mismo cupo.
    enforce_upload_limits(settings, admin)
    limit_mb = settings.company_docs_max_file_mb
    _reject_oversized_body(request, limit_mb)
    content = await _read_limited(file, limit_mb)
    document = await use_case.execute(
        document_id, filename=file.filename or "documento", content=content
    )
    return _response(document)


@router.post("/{document_id}/reprocess", response_model=CompanyDocumentResponse)
async def reprocess_document(
    document_id: UUID, use_case: ReprocessUseCaseDep, _admin: SaviAdminDep
) -> CompanyDocumentResponse:
    return _response(await use_case.execute(document_id))


@router.post("/{document_id}/read-with-ai", response_model=CompanyDocumentResponse)
async def read_document_with_ai(
    document_id: UUID, use_case: ReadWithAiUseCaseDep, _admin: SaviAdminDep
) -> CompanyDocumentResponse:
    """Descarta lo leído con IA de la versión vigente y lo vuelve a leer."""
    return _response(await use_case.execute(document_id))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID, use_case: DeleteUseCaseDep, _admin: SaviAdminDep
) -> None:
    """Baja: borra archivo y fragmentos, y lo retira del índice en el acto.

    Idempotente para el cliente: eliminar dos veces devuelve 204 las dos.
    """
    await use_case.execute(document_id)
