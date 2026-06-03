from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from app.modules.auth.infrastructure.http import CurrentUserDep
from app.modules.usage.application.responses import (
    SystemUsageReportResponse,
    UserUsageReportResponse,
)
from app.modules.usage.domain.value_objects import UsagePeriod
from app.modules.usage.infrastructure.http.dependencies import (
    AdminUserDep,
    GetSystemUsageUseCaseDep,
    GetUserUsageUseCaseDep,
    SettingsDep,
)

router = APIRouter(prefix="/usage", tags=["usage"])

_DEFAULT_WINDOW_DAYS = 30


def _resolve_period(start: datetime | None, end: datetime | None) -> UsagePeriod:
    """Período consultado. Default: últimos 30 días hasta ahora.

    Si vienen sin timezone (el cliente mandó una fecha "naive"), se asume
    UTC para no romper la comparación con `created_at` (timestamptz).
    """
    now = datetime.now(UTC)
    resolved_end = _ensure_utc(end) if end is not None else now
    resolved_start = (
        _ensure_utc(start)
        if start is not None
        else resolved_end - timedelta(days=_DEFAULT_WINDOW_DAYS)
    )
    return UsagePeriod(start=resolved_start, end=resolved_end)


def _ensure_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@router.get("/me", response_model=UserUsageReportResponse)
async def my_usage(
    use_case: GetUserUsageUseCaseDep,
    user: CurrentUserDep,
    settings: SettingsDep,
    start: datetime | None = Query(
        default=None, description="Inicio del período (ISO 8601). Default: hace 30 días."
    ),
    end: datetime | None = Query(
        default=None, description="Fin del período (ISO 8601). Default: ahora."
    ),
) -> UserUsageReportResponse:
    """Consumo del usuario autenticado: total + serie diaria, en USD.

    Incluye `usd_to_cop_rate` para que la vista muestre el equivalente en
    pesos colombianos.
    """
    period = _resolve_period(start, end)
    report = await use_case.execute(user.id, period)
    return UserUsageReportResponse.from_dto(
        report, usd_to_cop_rate=settings.usd_to_cop_rate
    )


@router.get("/system", response_model=SystemUsageReportResponse)
async def system_usage(
    use_case: GetSystemUsageUseCaseDep,
    _admin: AdminUserDep,
    settings: SettingsDep,
    start: datetime | None = Query(
        default=None, description="Inicio del período (ISO 8601). Default: hace 30 días."
    ),
    end: datetime | None = Query(
        default=None, description="Fin del período (ISO 8601). Default: ahora."
    ),
) -> SystemUsageReportResponse:
    """Consumo global del sistema (solo admins): total + ranking por
    usuario + serie diaria. 403 si el usuario no es admin.
    """
    period = _resolve_period(start, end)
    report = await use_case.execute(period)
    return SystemUsageReportResponse.from_dto(
        report, usd_to_cop_rate=settings.usd_to_cop_rate
    )
