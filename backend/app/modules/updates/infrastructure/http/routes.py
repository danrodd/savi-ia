from fastapi import APIRouter, Request, status

from app.modules.auth.infrastructure.http import CurrentUserDep
from app.modules.auth.infrastructure.http.admin import SaviAdminDep
from app.modules.updates.application.responses import UpdateStatusResponse
from app.modules.updates.domain.exceptions import (
    NoUpdateAvailableError,
    RemoteUpdateNotAllowedError,
)
from app.modules.updates.infrastructure.provider import get_update_coordinator

router = APIRouter(prefix="/updates", tags=["updates"])

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _is_local(request: Request) -> bool:
    """El pedido sale del mismo equipo donde corre SAVI.

    En una instalación en servidor, quien entra desde otro equipo no puede
    aceptar el UAC que aparece en el servidor: actualiza sistemas, ahí.
    """
    return request.client is not None and request.client.host in _LOOPBACK


@router.get("/status", response_model=UpdateStatusResponse)
async def update_status(request: Request, _user: CurrentUserDep) -> UpdateStatusResponse:
    coordinator = get_update_coordinator()
    if coordinator is None:
        return UpdateStatusResponse.disabled()
    return UpdateStatusResponse.from_snapshot(coordinator.snapshot(), can_apply=_is_local(request))


@router.post("/apply", response_model=UpdateStatusResponse, status_code=status.HTTP_202_ACCEPTED)
async def apply_update(request: Request, _user: CurrentUserDep) -> UpdateStatusResponse:
    """Descarga, verifica y lanza el instalador en segundo plano.

    Vuelve enseguida: el avance se sigue con `GET /updates/status`.
    """
    coordinator = get_update_coordinator()
    if coordinator is None:
        raise NoUpdateAvailableError()
    if not _is_local(request):
        raise RemoteUpdateNotAllowedError()
    coordinator.start_apply()
    return UpdateStatusResponse.from_snapshot(coordinator.snapshot(), can_apply=True)


@router.post("/check", response_model=UpdateStatusResponse)
async def check_now(request: Request, _admin: SaviAdminDep) -> UpdateStatusResponse:
    """Chequea ya, sin esperar el próximo ciclo. Para soporte y para probar."""
    coordinator = get_update_coordinator()
    if coordinator is None:
        return UpdateStatusResponse.disabled()
    await coordinator.check()
    return UpdateStatusResponse.from_snapshot(coordinator.snapshot(), can_apply=_is_local(request))
