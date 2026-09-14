from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Query

from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http import CurrentUserDep
from app.modules.usage.application.responses import (
    ConversationUsageResponse,
    SystemUsageReportResponse,
    UsageKpisResponse,
    UserUsageReportResponse,
)
from app.modules.usage.domain.value_objects import UsageFilters, UsagePeriod
from app.modules.usage.infrastructure.http.dependencies import (
    AdminUserDep,
    GetSystemUsageUseCaseDep,
    GetUsageKpisUseCaseDep,
    GetUserUsageUseCaseDep,
    ListConversationUsageUseCaseDep,
    SettingsDep,
)

router = APIRouter(prefix="/usage", tags=["usage"])

_DEFAULT_WINDOW_DAYS = 30
# Tope de filas del detalle por conversación (tabla + CSV). Generoso para
# pre-producción; evita payloads enormes si el volumen crece.
_CONVERSATIONS_LIMIT_DEFAULT = 500
_CONVERSATIONS_LIMIT_MAX = 5000


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


def _require_database(user: AuthenticatedUser) -> UUID:
    """Base del ERP del usuario autenticado.

    Nunca es `None`: el token ya no se puede decodificar sin base.
    """
    assert user.erp_database_id is not None  # noqa: S101
    return user.erp_database_id


def _resolve_filters(provider: str | None, model: str | None) -> UsageFilters:
    return UsageFilters(provider=provider, model=model)


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
    provider: str | None = Query(default=None, description="Proveedor del modelo."),
    model: str | None = Query(default=None, description="Modelo utilizado."),
) -> UserUsageReportResponse:
    """Consumo del usuario autenticado: total + serie diaria, en USD.

    Incluye `usd_to_cop_rate` para que la vista muestre el equivalente en
    pesos colombianos.
    """
    period = _resolve_period(start, end)
    report = await use_case.execute(
        user.id,
        period,
        erp_database_id=_require_database(user),
        filters=_resolve_filters(provider, model),
    )
    return UserUsageReportResponse.from_dto(report, usd_to_cop_rate=settings.usd_to_cop_rate)


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
    provider: str | None = Query(default=None, description="Proveedor del modelo."),
    model: str | None = Query(default=None, description="Modelo utilizado."),
) -> SystemUsageReportResponse:
    """Consumo global del sistema (solo admins): total + ranking por
    usuario + serie diaria. 403 si el usuario no es admin.
    """
    period = _resolve_period(start, end)
    report = await use_case.execute(period, filters=_resolve_filters(provider, model))
    return SystemUsageReportResponse.from_dto(report, usd_to_cop_rate=settings.usd_to_cop_rate)


@router.get("/kpis", response_model=UsageKpisResponse)
async def usage_kpis(
    use_case: GetUsageKpisUseCaseDep,
    _admin: AdminUserDep,
    settings: SettingsDep,
    start: datetime | None = Query(
        default=None, description="Inicio del período (ISO 8601). Default: hace 30 días."
    ),
    end: datetime | None = Query(
        default=None, description="Fin del período (ISO 8601). Default: ahora."
    ),
    provider: str | None = Query(default=None, description="Proveedor del modelo."),
    model: str | None = Query(default=None, description="Modelo utilizado."),
) -> UsageKpisResponse:
    """KPIs de consumo para definir tarifa (solo admins).

    Incluye percentiles por conversación (p50/p90/p95), costo por turno,
    proyección mensual al ritmo actual y ratio de caché. 403 si no es admin.
    """
    period = _resolve_period(start, end)
    kpis = await use_case.execute(period, filters=_resolve_filters(provider, model))
    return UsageKpisResponse.from_dto(kpis, usd_to_cop_rate=settings.usd_to_cop_rate)


@router.get("/conversations", response_model=list[ConversationUsageResponse])
async def conversations_usage(
    use_case: ListConversationUsageUseCaseDep,
    _admin: AdminUserDep,
    start: datetime | None = Query(
        default=None, description="Inicio del período (ISO 8601). Default: hace 30 días."
    ),
    end: datetime | None = Query(
        default=None, description="Fin del período (ISO 8601). Default: ahora."
    ),
    provider: str | None = Query(default=None, description="Proveedor del modelo."),
    model: str | None = Query(default=None, description="Modelo utilizado."),
    limit: int = Query(
        default=_CONVERSATIONS_LIMIT_DEFAULT,
        ge=1,
        le=_CONVERSATIONS_LIMIT_MAX,
        description="Máximo de conversaciones a devolver (las más caras primero).",
    ),
) -> list[ConversationUsageResponse]:
    """Consumo por conversación, de la más cara a la más barata (solo admins).

    Alimenta la tabla de conversaciones pesadas, el histograma de
    distribución y el export CSV de la vista de KPIs.
    """
    period = _resolve_period(start, end)
    rows = await use_case.execute(
        period,
        limit=limit,
        filters=_resolve_filters(provider, model),
    )
    return [ConversationUsageResponse.from_vo(r) for r in rows]
