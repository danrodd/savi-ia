"""Endpoints de fuentes web (Fase 5).

Todo bajo `/admin/company-web-sources` con `SaviAdminDep`, como los
documentos. El administrador de una empresa solo ve las fuentes que aplican
a su base; el de la instalación ve todas.
"""

from uuid import UUID

from fastapi import APIRouter, status

from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.admin import SaviAdminDep, is_platform_admin
from app.modules.company_knowledge.application.requests import (
    CreateWebSourceRequest,
    PreviewWebSourceRequest,
    UpdateWebSourceRequest,
)
from app.modules.company_knowledge.application.responses import (
    WebSourceDetailResponse,
    WebSourcePreviewResponse,
    WebSourceResponse,
)
from app.modules.company_knowledge.domain.entities.web_source import WebSource
from app.modules.company_knowledge.domain.exceptions import WebSourceNotFoundError
from app.modules.company_knowledge.infrastructure.http.dependencies import (
    ConfiguredUploadLimitDep,
    SettingsDep,
)
from app.modules.company_knowledge.infrastructure.http.web_dependencies import (
    CreateWebSourceUseCaseDep,
    DeleteWebSourceUseCaseDep,
    GetWebSourceUseCaseDep,
    ListWebSourcesUseCaseDep,
    PreviewWebSourceUseCaseDep,
    RefreshWebSourceUseCaseDep,
    UpdateWebSourceUseCaseDep,
)
from app.shared.rate_limit import enforce_upload_limits

router = APIRouter(prefix="/admin/company-web-sources", tags=["company-web-sources"])


def _visible_to(source: WebSource, admin: AuthenticatedUser, platform_admin: bool) -> bool:
    if platform_admin:
        return True
    return source.all_databases or admin.erp_database_id in source.database_ids


@router.post("/preview", response_model=WebSourcePreviewResponse)
async def preview_web_source(
    request: PreviewWebSourceRequest,
    use_case: PreviewWebSourceUseCaseDep,
    settings: SettingsDep,
    _admin: SaviAdminDep,
) -> WebSourcePreviewResponse:
    """Qué aprendería SAVI de la URL, sin guardar nada."""
    preview = await use_case.execute(
        request.url.strip(),
        mode=request.mode,
        max_pages=min(request.max_pages, settings.company_web_max_pages_per_source),
        excluded_sections=request.excluded_sections,
    )
    return WebSourcePreviewResponse.from_preview(preview)


@router.post("", response_model=WebSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_web_source(
    request: CreateWebSourceRequest,
    use_case: CreateWebSourceUseCaseDep,
    settings: SettingsDep,
    admin: SaviAdminDep,
    upload_limit: ConfiguredUploadLimitDep,
) -> WebSourceResponse:
    # Cada alta encola un rastreo: cuenta para el mismo cupo que las subidas.
    enforce_upload_limits(settings, admin, upload_limit)
    assert admin.erp_database_id is not None  # noqa: S101 — el token no decodifica sin base
    source = await use_case.execute(
        url=request.url,
        mode=request.mode,
        title=request.title,
        refresh=request.refresh,
        max_pages=request.max_pages,
        excluded_sections=request.excluded_sections,
        visibility=request.visibility,
        modules=request.modules,
        all_databases=request.all_databases,
        database_ids=request.database_ids,
        created_by_login=admin.login,
        created_by_database_id=admin.erp_database_id,
        created_by_user_id=admin.id,
    )
    return WebSourceResponse.from_entity(source)


@router.get("", response_model=list[WebSourceResponse])
async def list_web_sources(
    use_case: ListWebSourcesUseCaseDep, settings: SettingsDep, admin: SaviAdminDep
) -> list[WebSourceResponse]:
    platform_admin = await is_platform_admin(admin, settings)
    return [
        WebSourceResponse.from_entity(source)
        for source in await use_case.execute()
        if _visible_to(source, admin, platform_admin)
    ]


@router.get("/{source_id}", response_model=WebSourceDetailResponse)
async def get_web_source(
    source_id: UUID, use_case: GetWebSourceUseCaseDep, settings: SettingsDep, admin: SaviAdminDep
) -> WebSourceDetailResponse:
    detail = await use_case.execute(source_id)
    if not _visible_to(detail.source, admin, await is_platform_admin(admin, settings)):
        raise WebSourceNotFoundError(str(source_id))
    return WebSourceDetailResponse.from_detail(detail)


@router.patch("/{source_id}", response_model=WebSourceResponse)
async def update_web_source(
    source_id: UUID,
    request: UpdateWebSourceRequest,
    use_case: UpdateWebSourceUseCaseDep,
    _admin: SaviAdminDep,
) -> WebSourceResponse:
    """Edita la fuente. Los permisos aplican en la siguiente pregunta."""
    source = await use_case.execute(
        source_id,
        title=request.title,
        refresh=request.refresh,
        max_pages=request.max_pages,
        excluded_sections=request.excluded_sections,
        visibility=request.visibility,
        modules=request.modules,
        all_databases=request.all_databases,
        database_ids=request.database_ids,
    )
    return WebSourceResponse.from_entity(source)


@router.post("/{source_id}/refresh", response_model=WebSourceResponse)
async def refresh_web_source(
    source_id: UUID,
    use_case: RefreshWebSourceUseCaseDep,
    settings: SettingsDep,
    admin: SaviAdminDep,
    upload_limit: ConfiguredUploadLimitDep,
) -> WebSourceResponse:
    enforce_upload_limits(settings, admin, upload_limit)
    return WebSourceResponse.from_entity(await use_case.execute(source_id))


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_web_source(
    source_id: UUID, use_case: DeleteWebSourceUseCaseDep, _admin: SaviAdminDep
) -> None:
    """Baja: sus páginas salen del índice en el acto. Idempotente."""
    await use_case.execute(source_id)
