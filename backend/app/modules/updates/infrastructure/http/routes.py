from fastapi import APIRouter, Request, status

from app.infrastructure.config import get_settings
from app.modules.auth.infrastructure.http import CurrentUserDep
from app.modules.auth.infrastructure.http.admin import SaviAdminDep
from app.modules.updates.application.responses import (
    InstallRecordResponse,
    UpdateHistoryResponse,
    UpdateStatusResponse,
)
from app.modules.updates.domain.exceptions import (
    NoUpdateAvailableError,
    RemoteUpdateNotAllowedError,
)
from app.modules.updates.domain.value_objects import HISTORY_LIMIT
from app.modules.updates.infrastructure.provider import get_update_coordinator, update_url

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


@router.get("/history", response_model=UpdateHistoryResponse)
async def install_history(_admin: SaviAdminDep) -> UpdateHistoryResponse:
    """Canal, servidor y los últimos intentos de instalación (del más reciente al más viejo).

    El canal y el servidor son datos de la instalación: solo los ve un administrador.
    """
    settings = get_settings()
    coordinator = get_update_coordinator()
    records = coordinator.install_history(HISTORY_LIMIT) if coordinator is not None else []
    return UpdateHistoryResponse(
        channel=settings.update_channel,
        server=update_url(settings) if coordinator is not None else "",
        records=[InstallRecordResponse.from_record(record) for record in records],
    )
