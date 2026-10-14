"""Métricas de la consola: resumen, uso por cliente, sucursales y usuarios (§3.1, §3.2, §4)."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_clock, transaction
from app.modules.alerts.domain import Severity
from app.modules.alerts.infrastructure import SqlAlchemyAlertRepository
from app.modules.clients.domain import ClientNotFound
from app.modules.clients.infrastructure import ClientModel
from app.modules.console.queries import is_online
from app.modules.instances.infrastructure import InstanceModel, to_entity
from app.modules.metrics.definitions import METRICS
from app.modules.metrics.queries import (
    ClientMetrics,
    DatabaseInfo,
    DayPoint,
    MetricsQueries,
    Period,
    Totals,
)
from app.modules.staff.application import Principal
from app.modules.staff.dependencies import RequirePermission
from app.modules.staff.domain import Permission
from app.shared.clock import Clock, as_utc

router = APIRouter(prefix="/console/api", tags=["console-metrics"])


# ------------------------------------------------------------------ respuestas


class DefinitionOut(BaseModel):
    key: str
    label: str
    definition: str
    source: str


class PeriodOut(BaseModel):
    start: datetime
    end: datetime


class UsageOut(BaseModel):
    turns: int
    conversations: int
    active_users: int
    entering_users: int
    adoption: float | None
    tokens: int
    cost_usd: str
    cost_per_active_user: str | None
    turns_without_price: int
    turns_with_error: int
    turns_interrupted: int
    turns_truncated: int
    error_rate: float | None
    latency_p50_ms: int | None
    latency_p90_ms: int | None
    free_queries: int
    free_queries_failed: int

    @classmethod
    def of(cls, t: Totals) -> UsageOut:
        per_user = t.cost_per_active_user
        return cls(
            turns=t.turns,
            conversations=t.conversations,
            active_users=t.active_users,
            entering_users=t.entering_users,
            adoption=t.adoption,
            tokens=t.tokens,
            cost_usd=str(t.cost_usd),
            cost_per_active_user=f"{per_user:.6f}" if per_user is not None else None,
            turns_without_price=t.turns_without_price,
            turns_with_error=t.turns_with_error,
            turns_interrupted=t.turns_interrupted,
            turns_truncated=t.turns_truncated,
            error_rate=t.error_rate,
            latency_p50_ms=t.latency_p50_ms,
            latency_p90_ms=t.latency_p90_ms,
            free_queries=t.free_queries,
            free_queries_failed=t.free_queries_failed,
        )


class DayOut(BaseModel):
    day: date
    turns: int
    active_users: int
    tokens: int
    cost_usd: str
    turns_with_error: int
    latency_p50_ms: int | None
    latency_p90_ms: int | None

    @classmethod
    def of(cls, p: DayPoint) -> DayOut:
        return cls(
            day=p.day,
            turns=p.turns,
            active_users=p.active_users,
            tokens=p.tokens,
            cost_usd=str(p.cost_usd),
            turns_with_error=p.turns_with_error,
            latency_p50_ms=p.latency_p50_ms,
            latency_p90_ms=p.latency_p90_ms,
        )


class ModelOut(BaseModel):
    provider: str | None
    model: str | None
    turns: int
    tokens: int
    cost_usd: str


class DatabaseUsageOut(BaseModel):
    database_ref: str | None
    name: str | None
    turns: int
    tokens: int
    cost_usd: str


class ToolOut(BaseModel):
    name: str
    tipo: str | None
    uses: int
    errors: int


class FreshnessOut(BaseModel):
    """«Datos hasta hace N segundos». `None` = todavía no hay ninguna instancia con datos."""

    seconds: int | None
    last_seen_at: datetime | None


class ClientMetricsOut(BaseModel):
    period: PeriodOut
    freshness: FreshnessOut
    totals: UsageOut
    series: list[DayOut]
    by_model: list[ModelOut]
    by_database: list[DatabaseUsageOut]
    tools: list[ToolOut]
    finish_reasons: dict[str, int]


class DatabaseOut(BaseModel):
    database_ref: str
    code: str
    name: str
    is_active: bool
    is_usable: bool
    credentials_unreadable: bool
    last_connection_ok_at: datetime | None
    snapshot_date: date

    @classmethod
    def of(cls, d: DatabaseInfo) -> DatabaseOut:
        return cls(
            database_ref=str(d.database_ref),
            code=d.code,
            name=d.name,
            is_active=d.is_active,
            is_usable=d.is_usable,
            credentials_unreadable=d.credentials_unreadable,
            last_connection_ok_at=d.last_connection_ok_at,
            snapshot_date=d.snapshot_date,
        )


class UserOut(BaseModel):
    user_ref: str
    turns: int
    cost_usd: str
    last_used_at: datetime
    databases_used: int


class CountsOut(BaseModel):
    active: int
    suspended: int


class InstanceCountsOut(BaseModel):
    online: int
    offline: int
    suspended: int
    revoked: int


class VersionOut(BaseModel):
    version: str | None
    instances: int


class OverviewOut(BaseModel):
    clients: CountsOut
    instances: InstanceCountsOut
    period: PeriodOut
    freshness: FreshnessOut
    usage: UsageOut
    trend: list[DayOut]
    providers: list[ModelOut]
    versions: list[VersionOut]
    open_alerts: dict[str, int]


# ------------------------------------------------------------------ utilidades


def _period(request: Request, start: datetime | None, end: datetime | None) -> Period:
    clock: Clock = get_clock(request)
    return Period.resolve(start, end, clock())


def _streams_oldest(heartbeat: dict[str, Any] | None) -> datetime | None:
    """Marca más vieja entre los streams que la instancia informó en su último heartbeat."""
    sync: dict[str, Any] = (heartbeat or {}).get("sync") or {}
    streams: dict[str, Any] = sync.get("streams") or {}
    marks: list[datetime] = []
    for info in streams.values():
        stream_info: dict[str, Any] = info or {}
        raw = stream_info.get("watermark_at")
        if isinstance(raw, str):
            try:
                marks.append(as_utc(datetime.fromisoformat(raw.replace("Z", "+00:00"))))
            except ValueError:
                continue
    return min(marks) if marks else None


async def _freshness(session: AsyncSession, now: datetime, client_id: UUID | None) -> FreshnessOut:
    """Lo más atrasado entre `now - last_seen_at` y la marca más vieja de los streams.

    Con varias instancias se toma la peor (la más conservadora): un solo equipo sin conexión
    hace que los totales del cliente estén incompletos.
    """
    stmt = select(InstanceModel).where(InstanceModel.status != "revoked")
    if client_id is not None:
        stmt = stmt.where(InstanceModel.client_id == client_id)
    worst: float | None = None
    last_seen: datetime | None = None
    for model in (await session.execute(stmt)).scalars():
        instance = to_entity(model)
        if instance.last_seen_at is None:
            continue
        last_seen = max(last_seen, instance.last_seen_at) if last_seen else instance.last_seen_at
        staleness = (now - instance.last_seen_at).total_seconds()
        oldest = _streams_oldest(instance.last_heartbeat)
        if oldest is not None:
            staleness = max(staleness, (now - oldest).total_seconds())
        worst = staleness if worst is None else max(worst, staleness)
    return FreshnessOut(
        seconds=max(0, round(worst)) if worst is not None else None, last_seen_at=last_seen
    )


def _models(rows: Any) -> list[ModelOut]:
    return [
        ModelOut(
            provider=r.provider,
            model=r.model,
            turns=r.turns,
            tokens=r.tokens,
            cost_usd=str(r.cost_usd),
        )
        for r in rows
    ]


# ------------------------------------------------------------------ rutas


@router.get("/metric-definitions", response_model=list[DefinitionOut])
async def metric_definitions(
    _: Principal = Depends(RequirePermission(Permission.OVERVIEW_READ)),
) -> list[DefinitionOut]:
    return [
        DefinitionOut(key=m.key, label=m.label, definition=m.definition, source=m.source)
        for m in METRICS
    ]


@router.get("/overview", response_model=OverviewOut)
async def overview(
    request: Request,
    start: datetime | None = None,
    end: datetime | None = None,
    _: Principal = Depends(RequirePermission(Permission.OVERVIEW_READ)),
) -> OverviewOut:
    period = _period(request, start, end)
    now = get_clock(request)()
    async with transaction(request) as session:
        queries = MetricsQueries(session)
        by_status = dict(
            (
                await session.execute(
                    select(ClientModel.status, func.count()).group_by(ClientModel.status)
                )
            ).all()
        )
        instances = [to_entity(m) for m in (await session.execute(select(InstanceModel))).scalars()]
        totals = await queries.totals(None, period)
        series = await queries.series(None, period)
        providers = await queries.by_model(None, period)
        freshness = await _freshness(session, now, None)
        open_alerts = await SqlAlchemyAlertRepository(session).count_open_by_severity()

    live = [i for i in instances if i.status.value != "revoked"]
    online = sum(1 for i in live if i.status.value == "active" and is_online(i.last_seen_at, now))
    active_instances = [i for i in live if i.status.value == "active"]
    versions = Counter(i.version for i in live)
    return OverviewOut(
        clients=CountsOut(
            active=int(by_status.get("active", 0)), suspended=int(by_status.get("suspended", 0))
        ),
        instances=InstanceCountsOut(
            online=online,
            offline=len(active_instances) - online,
            suspended=sum(1 for i in instances if i.status.value == "suspended"),
            revoked=sum(1 for i in instances if i.status.value == "revoked"),
        ),
        period=PeriodOut(start=period.start, end=period.end),
        freshness=freshness,
        usage=UsageOut.of(totals),
        trend=[DayOut.of(p) for p in series],
        providers=_models(providers),
        versions=[
            VersionOut(version=v, instances=n)
            for v, n in sorted(versions.items(), key=lambda kv: (-kv[1], str(kv[0])))
        ],
        open_alerts={s.value: open_alerts.get(s, 0) for s in Severity},
    )


async def _require_client(session: AsyncSession, client_id: UUID) -> None:
    if await session.get(ClientModel, client_id) is None:
        raise ClientNotFound("No existe el cliente.")


@router.get("/clients/{client_id}/metrics", response_model=ClientMetricsOut)
async def client_metrics(
    client_id: UUID,
    request: Request,
    start: datetime | None = None,
    end: datetime | None = None,
    _: Principal = Depends(RequirePermission(Permission.CLIENTS_READ)),
) -> ClientMetricsOut:
    period = _period(request, start, end)
    now = get_clock(request)()
    async with transaction(request) as session:
        await _require_client(session, client_id)
        metrics: ClientMetrics = await MetricsQueries(session).client_metrics(client_id, period)
        freshness = await _freshness(session, now, client_id)
    return ClientMetricsOut(
        period=PeriodOut(start=period.start, end=period.end),
        freshness=freshness,
        totals=UsageOut.of(metrics.totals),
        series=[DayOut.of(p) for p in metrics.series],
        by_model=_models(metrics.by_model),
        by_database=[
            DatabaseUsageOut(
                database_ref=str(d.database_ref) if d.database_ref else None,
                name=d.name,
                turns=d.turns,
                tokens=d.tokens,
                cost_usd=str(d.cost_usd),
            )
            for d in metrics.by_database
        ],
        tools=[
            ToolOut(name=t.name, tipo=t.tipo, uses=t.uses, errors=t.errors) for t in metrics.tools
        ],
        finish_reasons=metrics.finish_reasons,
    )


@router.get("/clients/{client_id}/databases", response_model=list[DatabaseOut])
async def client_databases(
    client_id: UUID,
    request: Request,
    _: Principal = Depends(RequirePermission(Permission.CLIENTS_READ)),
) -> list[DatabaseOut]:
    async with transaction(request) as session:
        await _require_client(session, client_id)
        rows = await MetricsQueries(session).databases(client_id)
    return [DatabaseOut.of(d) for d in rows]


@router.get("/clients/{client_id}/users", response_model=list[UserOut])
async def client_users(
    client_id: UUID,
    request: Request,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _: Principal = Depends(RequirePermission(Permission.CLIENTS_READ)),
) -> list[UserOut]:
    """Ranking por seudónimo: Cloud nunca recibe nombres ni correos de las personas."""
    period = _period(request, start, end)
    async with transaction(request) as session:
        await _require_client(session, client_id)
        rows = await MetricsQueries(session).users(client_id, period, limit)
    return [
        UserOut(
            user_ref=u.user_ref,
            turns=u.turns,
            cost_usd=str(u.cost_usd),
            last_used_at=u.last_used_at,
            databases_used=u.databases_used,
        )
        for u in rows
    ]
