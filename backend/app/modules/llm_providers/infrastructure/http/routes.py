"""Endpoints de administración de los proveedores de IA.

Todos bajo `/admin/llm-providers` y protegidos por `SaviAdminDep`. La
credencial entra por el body y nunca sale por ninguna respuesta.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.modules.auth.infrastructure.http.admin import PlatformAdminDep
from app.modules.llm_providers.application.requests import (
    SaveLlmProviderRequest,
    TestLlmProviderRequest,
)
from app.modules.llm_providers.application.responses import (
    LlmProviderResponse,
    ModelInfoResponse,
    ModelListResponse,
    ProviderTestResponse,
)
from app.modules.llm_providers.infrastructure.http.dependencies import (
    ManageLlmProvidersUseCaseDep,
)

router = APIRouter(prefix="/admin/llm-providers", tags=["llm-providers"])


@router.get("", response_model=list[LlmProviderResponse])
async def list_providers(
    use_case: ManageLlmProvidersUseCaseDep,
    _admin: PlatformAdminDep,
) -> list[LlmProviderResponse]:
    """Un item por proveedor soportado, configurado o no."""
    return [LlmProviderResponse.from_dto(d) for d in await use_case.list()]


@router.put("/{provider}", response_model=LlmProviderResponse)
async def save_provider(
    provider: str,
    request: SaveLlmProviderRequest,
    use_case: ManageLlmProvidersUseCaseDep,
    _admin: PlatformAdminDep,
) -> LlmProviderResponse:
    return LlmProviderResponse.from_dto(await use_case.save(provider, request.to_dto()))


@router.post("/{provider}/test", response_model=ProviderTestResponse)
async def test_provider(
    provider: str,
    request: TestLlmProviderRequest,
    use_case: ManageLlmProvidersUseCaseDep,
    _admin: PlatformAdminDep,
) -> ProviderTestResponse:
    """No persiste la configuración. Devuelve 200 aunque la credencial
    falle: el resultado va en `ok`."""
    return ProviderTestResponse.from_result(await use_case.test(provider, request.to_dto()))


@router.get("/{provider}/models", response_model=ModelListResponse)
async def list_models(
    provider: str,
    use_case: ManageLlmProvidersUseCaseDep,
    _admin: PlatformAdminDep,
) -> ModelListResponse:
    models = await use_case.list_models(provider)
    return ModelListResponse(models=[ModelInfoResponse.from_value(m) for m in models])


@router.post("/{provider}/activate", response_model=LlmProviderResponse)
async def activate_provider(
    provider: str,
    use_case: ManageLlmProvidersUseCaseDep,
    _admin: PlatformAdminDep,
) -> LlmProviderResponse:
    return LlmProviderResponse.from_dto(await use_case.activate(provider))
