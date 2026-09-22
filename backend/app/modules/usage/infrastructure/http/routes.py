from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

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
from app.shared.exceptions import ValidationError

router = APIRouter(prefix="/usage", tags=["usage"])

_DEFAULT_WINDOW_DAYS = 30
# Tope de filas del detalle por conversación (tabla + CSV). Generoso para
# pre-producción; evita payloads enormes si el volumen crece.
_CONVERSATIONS_LIMIT_DEFAULT = 500
_CONVERSATIONS_LIMIT_MAX = 5000

_FROM_DESC = (
    "Fecha de inicio (AAAA-MM-DD, inclusive), interpretada en la zona de "
    "reporte. Va junto con 'to'."
)
_TO_DESC = (
    "Fecha de fin (AAAA-MM-DD, inclusive), interpretada en la zona de "
    "reporte. Va junto con 'from'."
)
_PROVIDER_DESC = "Proveedor(es) del modelo. Repetible: ?provider=claude&provider=gemini."


def _period_from_dates(from_date: date, to_date: date, tz_name: str) -> UsagePeriod:
    """Corte de día en la zona de REPORTE, no en instantes UTC crudos.

    "Hoy" tiene que significar el día calendario de Bogotá, no "las
    últimas 24 horas" — si no, un turno de anoche se cuenta o se pierde
    según la hora en que se consulte. `to_date` es inclusivo: el fin real
    es el arranque del día siguiente.
    """
    tz = ZoneInfo(tz_name)
    start = datetime.combine(from_date, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return UsagePeriod(start=start, end=end)


def _resolve_period(
    start: datetime | None,
    end: datetime | None,
    from_date: date | None,
    to_date: date | None,
    *,
    reporting_timezone: str,
) -> UsagePeriod:
    """Período consultado. Default: últimos 30 días hasta ahora.

    `from`/`to` (solo fecha) tienen prioridad sobre `start`/`end` (instante
    ISO 8601) cuando ambos vienen — son el camino nuevo para los presets
    Hoy/Ayer, que necesitan el corte de día en zona local, no en UTC.
    """
    if from_date is not None or to_date is not None:
        if from_date is None or to_date is None:
            raise ValidationError("'from' y 'to' deben pasarse juntos.")
        return _period_from_dates(from_date, to_date, reporting_timezone)
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


def _resolve_filters(provider: list[str] | None, model: list[str] | None) -> UsageFilters:
    return UsageFilters(
        providers=frozenset(provider or ()),
        models=frozenset(model or ()),
    )


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
    from_date: date | None = Query(default=None, alias="from", description=_FROM_DESC),
    to_date: date | None = Query(default=None, alias="to", description=_TO_DESC),
    provider: list[str] | None = Query(default=None, description=_PROVIDER_DESC),
    model: list[str] | None = Query(default=None, description="Modelo(s) utilizado(s)."),
) -> UserUsageReportResponse:
    """Consumo del usuario autenticado: total + serie diaria, en USD.

    Incluye `usd_to_cop_rate` para que la vista muestre el equivalente en
    pesos colombianos.
    """
    period = _resolve_period(
        start, end, from_date, to_date, reporting_timezone=settings.reporting_timezone
    )
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
    from_date: date | None = Query(default=None, alias="from", description=_FROM_DESC),
    to_date: date | None = Query(default=None, alias="to", description=_TO_DESC),
    provider: list[str] | None = Query(default=None, description=_PROVIDER_DESC),
    model: list[str] | None = Query(default=None, description="Modelo(s) utilizado(s)."),
) -> SystemUsageReportResponse:
    """Consumo global del sistema (solo admins): total + ranking por
    usuario + serie diaria. 403 si el usuario no es admin.
    """
    period = _resolve_period(
        start, end, from_date, to_date, reporting_timezone=settings.reporting_timezone
    )
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
    from_date: date | None = Query(default=None, alias="from", description=_FROM_DESC),
    to_date: date | None = Query(default=None, alias="to", description=_TO_DESC),
    provider: list[str] | None = Query(default=None, description=_PROVIDER_DESC),
    model: list[str] | None = Query(default=None, description="Modelo(s) utilizado(s)."),
) -> UsageKpisResponse:
    """KPIs de consumo para definir tarifa (solo admins).

    Incluye percentiles por conversación (p50/p90/p95), costo por turno,
    proyección mensual al ritmo actual y ratio de caché. 403 si no es admin.
    """
    period = _resolve_period(
        start, end, from_date, to_date, reporting_timezone=settings.reporting_timezone
    )
    kpis = await use_case.execute(period, filters=_resolve_filters(provider, model))
    return UsageKpisResponse.from_dto(kpis, usd_to_cop_rate=settings.usd_to_cop_rate)


@router.get("/conversations", response_model=list[ConversationUsageResponse])
async def conversations_usage(
    use_case: ListConversationUsageUseCaseDep,
    _admin: AdminUserDep,
    settings: SettingsDep,
    start: datetime | None = Query(
        default=None, description="Inicio del período (ISO 8601). Default: hace 30 días."
    ),
    end: datetime | None = Query(
        default=None, description="Fin del período (ISO 8601). Default: ahora."
    ),
    from_date: date | None = Query(default=None, alias="from", description=_FROM_DESC),
    to_date: date | None = Query(default=None, alias="to", description=_TO_DESC),
    provider: list[str] | None = Query(default=None, description=_PROVIDER_DESC),
    model: list[str] | None = Query(default=None, description="Modelo(s) utilizado(s)."),
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
    period = _resolve_period(
        start, end, from_date, to_date, reporting_timezone=settings.reporting_timezone
    )
    rows = await use_case.execute(
        period,
        limit=limit,
        filters=_resolve_filters(provider, model),
    )
    return [ConversationUsageResponse.from_vo(r) for r in rows]
