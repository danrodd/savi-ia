"""Administración → SAVI Cloud (`/admin/cloud-link`).

Guard: administrador (`SaviAdminDep`), igual que el resto de `/admin`. Ninguna
respuesta lleva el secreto de la instancia ni la clave de seudónimos.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse

from app.modules.auth.infrastructure.http.admin import SaviAdminDep
from app.modules.cloud_link.application.requests import LinkCloudRequest
from app.modules.cloud_link.application.responses import (
    CloudLinkStatusResponse,
    PreviewResponse,
    SyncNowResponse,
)
from app.modules.cloud_link.domain.exceptions import CloudApiError, NotLinkedError
from app.modules.cloud_link.domain.value_objects import HistoryMode
from app.modules.cloud_link.infrastructure.composition import CloudLinkServices
from app.modules.cloud_link.infrastructure.http.dependencies import CloudLinkServicesDep

router = APIRouter(prefix="/admin/cloud-link", tags=["cloud-link"])

# Cómo se le cuenta al administrador un error de Cloud al vincular (§3.1).
_ENROLL_MESSAGES = {
    "enrollment_token_invalid": "El token no existe, venció o ya se usó.",
    "client_suspended": "El cliente está suspendido en SAVI Cloud.",
    "too_many_requests": "Demasiados intentos. Intente de nuevo en unos minutos.",
    "timeout": "SAVI Cloud no respondió a tiempo.",
    "network_error": "No se pudo conectar con SAVI Cloud. Revise la conexión a internet.",
}


def _enroll_error_response(error: CloudApiError) -> JSONResponse:
    code = error.error_code
    if error.status_code in (403, 404, 429):
        http_status = error.status_code
    elif error.status_code == 422:
        # Cloud rechazó lo que SAVI le mandó: es un defecto de contrato.
        http_status, code = status.HTTP_502_BAD_GATEWAY, "contract_rejected"
    else:
        http_status = status.HTTP_502_BAD_GATEWAY
    headers = (
        {"Retry-After": str(int(error.retry_after_seconds))}
        if error.retry_after_seconds is not None
        else None
    )
    detail = _ENROLL_MESSAGES.get(code, "SAVI Cloud no pudo completar la vinculación.")
    return JSONResponse(
        status_code=http_status,
        content={"errorCode": code, "detail": detail},
        headers=headers,
    )


async def _status_response(services: CloudLinkServices) -> CloudLinkStatusResponse:
    state, watermarks = await services.status()
    return CloudLinkStatusResponse.build(
        state,
        watermarks,
        cloud_configured=services.cloud_configured,
        sync_enabled=services.sync_enabled,
    )


@router.get("", response_model=CloudLinkStatusResponse)
async def get_cloud_link(
    _admin: SaviAdminDep, services: CloudLinkServicesDep
) -> CloudLinkStatusResponse:
    """Estado de la vinculación y marca de cada stream. Sin secretos."""
    return await _status_response(services)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CloudLinkStatusResponse)
async def link_cloud(
    body: LinkCloudRequest, _admin: SaviAdminDep, services: CloudLinkServicesDep
) -> CloudLinkStatusResponse | JSONResponse:
    """Vincula con SAVI Cloud canjeando el token. `422` si ya está vinculada."""
    try:
        await services.link.execute(
            cloud_url=services.settings.savi_cloud_url,
            token=body.token,
            history=HistoryMode(body.history),
        )
    except CloudApiError as error:
        return _enroll_error_response(error)
    services.wake()
    return await _status_response(services)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_cloud(_admin: SaviAdminDep, services: CloudLinkServicesDep) -> Response:
    """Desvincula localmente. Conserva la clave de seudónimos."""
    await services.unlink.execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sync-now", status_code=status.HTTP_202_ACCEPTED, response_model=SyncNowResponse)
async def sync_now(_admin: SaviAdminDep, services: CloudLinkServicesDep) -> SyncNowResponse:
    """Heartbeat y ciclo de envío inmediatos, en segundo plano."""
    state, _ = await services.status()
    if not state.has_credentials:
        raise NotLinkedError
    services.request_sync_now()
    return SyncNowResponse()


@router.get("/preview", response_model=PreviewResponse)
async def preview_cloud_payload(
    _admin: SaviAdminDep, services: CloudLinkServicesDep
) -> PreviewResponse:
    """Transparencia: el heartbeat y un evento real por stream, exactamente
    como viajarían."""
    preview = await services.preview.execute()
    return PreviewResponse(heartbeat=preview.heartbeat, events=preview.events)
