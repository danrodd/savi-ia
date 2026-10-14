"""Consultas de métricas sobre los eventos (definiciones en `definitions.py`).

Todas están acotadas por `(client_id, occurred_at)`, que es el índice de cada tabla de
eventos. Los días se agrupan en la zona `America/Bogota` (UTC-5, Colombia no tiene horario de
verano), con una expresión por dialecto: Postgres usa la zona; SQLite (tests) desplaza 5 h.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Date, Select, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modules.ingest.infrastructure import (
    EvConversationModel,
    EvFreeQueryModel,
    EvSessionModel,
    EvTurnModel,
    InstanceDatabaseModel,
)
from app.modules.metrics.definitions import (
    ERROR_FINISH_REASON,
    FREE_QUERY_SUCCESS,
    INTERRUPTED_FINISH_REASON,
    TRUNCATED_FINISH_REASON,
)

# Un SELECT con cualquier cantidad de columnas (el tipado de SQLAlchemy es invariante).
AnySelect = Select[*tuple[Any, ...]]

BOGOTA = "America/Bogota"
DEFAULT_PERIOD_DAYS = 30
MAX_PERIOD_DAYS = 400


@dataclass(frozen=True)
class Period:
    start: datetime
    end: datetime  # exclusivo

    @classmethod
    def resolve(cls, start: datetime | None, end: datetime | None, now: datetime) -> Period:
        end_value = (end or now + timedelta(seconds=1)).astimezone(UTC)
        start_value = (start or end_value - timedelta(days=DEFAULT_PERIOD_DAYS)).astimezone(UTC)
        return cls(start_value, end_value)

    @property
    def days(self) -> float:
        return (self.end - self.start).total_seconds() / 86400


def _day(session: AsyncSession, column: Any) -> ColumnElement[Any]:
    if session.get_bind().dialect.name == "postgresql":
        return cast(func.timezone(BOGOTA, column), Date)
    return func.date(column, "-5 hours")


def _money(value: Any) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal(0)


def percentile(values: list[int], fraction: float) -> int | None:
    """Percentil por rango más cercano (determinista y fácil de verificar a mano)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


@dataclass
class Totals:
    turns: int = 0
    conversations: int = 0
    active_users: int = 0
    entering_users: int = 0
    tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    turns_without_price: int = 0
    turns_with_error: int = 0
    turns_interrupted: int = 0
    turns_truncated: int = 0
    latency_p50_ms: int | None = None
    latency_p90_ms: int | None = None
    free_queries: int = 0
    free_queries_failed: int = 0

    @property
    def error_rate(self) -> float | None:
        return self.turns_with_error / self.turns if self.turns else None

    @property
    def adoption(self) -> float | None:
        return self.active_users / self.entering_users if self.entering_users else None

    @property
    def cost_per_active_user(self) -> Decimal | None:
        return self.cost_usd / self.active_users if self.active_users else None


@dataclass(frozen=True)
class DayPoint:
    day: date
    turns: int
    active_users: int
    tokens: int
    cost_usd: Decimal
    turns_with_error: int
    latency_p50_ms: int | None
    latency_p90_ms: int | None


@dataclass(frozen=True)
class ModelUsage:
    provider: str | None
    model: str | None
    turns: int
    tokens: int
    cost_usd: Decimal


@dataclass(frozen=True)
class DatabaseUsage:
    database_ref: UUID | None
    name: str | None
    turns: int
    tokens: int
    cost_usd: Decimal


@dataclass(frozen=True)
class ToolUsage:
    name: str
    tipo: str | None
    uses: int
    errors: int


@dataclass(frozen=True)
class UserUsage:
    user_ref: str
    turns: int
    cost_usd: Decimal
    last_used_at: datetime
    databases_used: int
    # Solo clientes en modo `named`; `None` para el resto.
    label: str | None = None


@dataclass(frozen=True)
class PersonActivity:
    """Una persona que inició sesión en una instalación."""

    user_ref: str
    label: str | None
    sessions: int
    last_session_at: datetime


@dataclass(frozen=True)
class DatabaseInfo:
    database_ref: UUID
    code: str
    name: str
    is_active: bool
    is_usable: bool
    credentials_unreadable: bool
    last_connection_ok_at: datetime | None
    snapshot_date: date


@dataclass
class ClientMetrics:
    totals: Totals
    series: list[DayPoint] = field(default_factory=lambda: [])
    by_model: list[ModelUsage] = field(default_factory=lambda: [])
    by_database: list[DatabaseUsage] = field(default_factory=lambda: [])
    tools: list[ToolUsage] = field(default_factory=lambda: [])
    finish_reasons: dict[str, int] = field(default_factory=lambda: {})


class MetricsQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ------------------------------------------------------------ filtros

    @staticmethod
    def _turn_scope(stmt: AnySelect, client_id: UUID | None, period: Period) -> AnySelect:
        stmt = stmt.where(
            EvTurnModel.occurred_at >= period.start, EvTurnModel.occurred_at < period.end
        )
        if client_id is not None:
            stmt = stmt.where(EvTurnModel.client_id == client_id)
        return stmt

    # ------------------------------------------------------------ totales

    async def totals(self, client_id: UUID | None, period: Period) -> Totals:
        t = EvTurnModel
        tokens = (
            t.input_tokens
            + t.output_tokens
            + t.cache_read_input_tokens
            + t.cache_creation_input_tokens
        )
        stmt = self._turn_scope(
            select(
                func.count(),
                func.count(func.distinct(t.user_ref)),
                func.coalesce(func.sum(tokens), 0),
                func.sum(t.cost_usd),
                func.sum(case((t.cost_usd.is_(None), 1), else_=0)),
                func.sum(case((t.finish_reason == ERROR_FINISH_REASON, 1), else_=0)),
                func.sum(case((t.finish_reason == INTERRUPTED_FINISH_REASON, 1), else_=0)),
                func.sum(case((t.finish_reason == TRUNCATED_FINISH_REASON, 1), else_=0)),
            ),
            client_id,
            period,
        )
        row = (await self._s.execute(stmt)).one()
        totals = Totals(
            turns=int(row[0]),
            active_users=int(row[1]),
            tokens=int(row[2] or 0),
            cost_usd=_money(row[3]),
            turns_without_price=int(row[4] or 0),
            turns_with_error=int(row[5] or 0),
            turns_interrupted=int(row[6] or 0),
            turns_truncated=int(row[7] or 0),
        )

        conv = select(func.count()).where(
            EvConversationModel.occurred_at >= period.start,
            EvConversationModel.occurred_at < period.end,
        )
        sess = select(func.count(func.distinct(EvSessionModel.user_ref))).where(
            EvSessionModel.occurred_at >= period.start, EvSessionModel.occurred_at < period.end
        )
        fq_total = select(func.count()).where(
            EvFreeQueryModel.occurred_at >= period.start,
            EvFreeQueryModel.occurred_at < period.end,
        )
        fq_failed = fq_total.where(EvFreeQueryModel.result != FREE_QUERY_SUCCESS)
        if client_id is not None:
            conv = conv.where(EvConversationModel.client_id == client_id)
            sess = sess.where(EvSessionModel.client_id == client_id)
            fq_total = fq_total.where(EvFreeQueryModel.client_id == client_id)
            fq_failed = fq_failed.where(EvFreeQueryModel.client_id == client_id)
        totals.conversations = int((await self._s.execute(conv)).scalar_one())
        totals.entering_users = int((await self._s.execute(sess)).scalar_one())
        totals.free_queries = int((await self._s.execute(fq_total)).scalar_one())
        totals.free_queries_failed = int((await self._s.execute(fq_failed)).scalar_one())

        latencies = await self._latencies(client_id, period)
        flat = [value for values in latencies.values() for value in values]
        totals.latency_p50_ms = percentile(flat, 0.5)
        totals.latency_p90_ms = percentile(flat, 0.9)
        return totals

    async def _latencies(self, client_id: UUID | None, period: Period) -> dict[date, list[int]]:
        day = _day(self._s, EvTurnModel.occurred_at)
        stmt = self._turn_scope(
            select(day, EvTurnModel.latency_ms).where(EvTurnModel.latency_ms.is_not(None)),
            client_id,
            period,
        )
        out: dict[date, list[int]] = defaultdict(list)
        for d, value in (await self._s.execute(stmt)).all():
            out[_as_date(d)].append(int(value))
        return out

    # ------------------------------------------------------------ serie diaria

    async def series(self, client_id: UUID | None, period: Period) -> list[DayPoint]:
        t = EvTurnModel
        day = _day(self._s, t.occurred_at).label("day")
        tokens = (
            t.input_tokens
            + t.output_tokens
            + t.cache_read_input_tokens
            + t.cache_creation_input_tokens
        )
        stmt = (
            self._turn_scope(
                select(
                    day,
                    func.count(),
                    func.count(func.distinct(t.user_ref)),
                    func.coalesce(func.sum(tokens), 0),
                    func.sum(t.cost_usd),
                    func.sum(case((t.finish_reason == ERROR_FINISH_REASON, 1), else_=0)),
                ),
                client_id,
                period,
            )
            .group_by(day)
            .order_by(day)
        )
        latencies = await self._latencies(client_id, period)
        points: list[DayPoint] = []
        for d, turns, users, toks, cost, errors in (await self._s.execute(stmt)).all():
            key = _as_date(d)
            values = latencies.get(key, [])
            points.append(
                DayPoint(
                    day=key,
                    turns=int(turns),
                    active_users=int(users),
                    tokens=int(toks or 0),
                    cost_usd=_money(cost),
                    turns_with_error=int(errors or 0),
                    latency_p50_ms=percentile(values, 0.5),
                    latency_p90_ms=percentile(values, 0.9),
                )
            )
        return points

    # ------------------------------------------------------------ desgloses

    async def by_model(self, client_id: UUID | None, period: Period) -> list[ModelUsage]:
        t = EvTurnModel
        tokens = (
            t.input_tokens
            + t.output_tokens
            + t.cache_read_input_tokens
            + t.cache_creation_input_tokens
        )
        stmt = (
            self._turn_scope(
                select(
                    t.provider,
                    t.model,
                    func.count(),
                    func.coalesce(func.sum(tokens), 0),
                    func.sum(t.cost_usd),
                ),
                client_id,
                period,
            )
            .group_by(t.provider, t.model)
            .order_by(func.count().desc())
        )
        return [
            ModelUsage(p, m, int(n), int(toks or 0), _money(cost))
            for p, m, n, toks, cost in (await self._s.execute(stmt)).all()
        ]

    async def by_database(self, client_id: UUID, period: Period) -> list[DatabaseUsage]:
        t = EvTurnModel
        tokens = (
            t.input_tokens
            + t.output_tokens
            + t.cache_read_input_tokens
            + t.cache_creation_input_tokens
        )
        stmt = (
            self._turn_scope(
                select(
                    t.database_ref,
                    func.count(),
                    func.coalesce(func.sum(tokens), 0),
                    func.sum(t.cost_usd),
                ),
                client_id,
                period,
            )
            .group_by(t.database_ref)
            .order_by(func.count().desc())
        )
        names = {d.database_ref: d.name for d in await self.databases(client_id)}
        return [
            DatabaseUsage(ref, names.get(ref) if ref else None, int(n), int(toks or 0), _money(c))
            for ref, n, toks, c in (await self._s.execute(stmt)).all()
        ]

    async def finish_reasons(self, client_id: UUID | None, period: Period) -> dict[str, int]:
        t = EvTurnModel
        stmt = self._turn_scope(select(t.finish_reason, func.count()), client_id, period).group_by(
            t.finish_reason
        )
        return {(reason or "unknown"): int(n) for reason, n in (await self._s.execute(stmt)).all()}

    async def tools(self, client_id: UUID | None, period: Period) -> list[ToolUsage]:
        stmt = self._turn_scope(select(EvTurnModel.tools), client_id, period)
        uses: Counter[tuple[str, str | None]] = Counter()
        errors: Counter[tuple[str, str | None]] = Counter()
        result = await self._s.stream(stmt)
        async for row in result:
            tools: list[dict[str, Any]] = row[0] or []
            for tool in tools:
                tipo = tool.get("tipo")
                key = (str(tool.get("name", "")), str(tipo) if tipo else None)
                uses[key] += 1
                if tool.get("status") == "error":
                    errors[key] += 1
        return [
            ToolUsage(name=name, tipo=tipo, uses=count, errors=errors[(name, tipo)])
            for (name, tipo), count in uses.most_common()
        ]

    async def users(self, client_id: UUID, period: Period, limit: int = 100) -> list[UserUsage]:
        t = EvTurnModel
        stmt = (
            self._turn_scope(
                select(
                    t.user_ref,
                    func.count(),
                    func.sum(t.cost_usd),
                    func.max(t.occurred_at),
                    func.count(func.distinct(t.database_ref)),
                ),
                client_id,
                period,
            )
            .group_by(t.user_ref)
            .order_by(func.count().desc(), t.user_ref)
            .limit(limit)
        )
        labels = await self._labels(client_id)
        return [
            UserUsage(ref, int(n), _money(cost), _utc(last), int(dbs), labels.get(ref))
            for ref, n, cost, last, dbs in (await self._s.execute(stmt)).all()
        ]

    async def _labels(self, client_id: UUID) -> dict[str, str]:
        """Última etiqueta conocida de cada persona (vacío si el cliente es `pseudonym`)."""
        s = EvSessionModel
        stmt = (
            select(s.user_ref, s.user_label)
            .where(s.client_id == client_id, s.user_label.is_not(None))
            .order_by(s.occurred_at)
        )
        # Orden ascendente: la última sesión pisa a las anteriores.
        return {ref: str(label) for ref, label in (await self._s.execute(stmt)).all()}

    async def people_of_instance(self, instance_id: UUID) -> list[PersonActivity]:
        """Quiénes entraron a esta instalación, con cuántas sesiones y cuándo fue la última."""
        s = EvSessionModel
        stmt = (
            select(s.user_ref, func.count(), func.max(s.occurred_at))
            .where(s.instance_id == instance_id)
            .group_by(s.user_ref)
            .order_by(func.max(s.occurred_at).desc())
        )
        labels_stmt = (
            select(s.user_ref, s.user_label)
            .where(s.instance_id == instance_id, s.user_label.is_not(None))
            .order_by(s.occurred_at)
        )
        labels = {ref: str(lbl) for ref, lbl in (await self._s.execute(labels_stmt)).all()}
        return [
            PersonActivity(ref, labels.get(ref), int(n), _utc(last))
            for ref, n, last in (await self._s.execute(stmt)).all()
        ]

    # ------------------------------------------------------------ inventario

    async def databases(self, client_id: UUID) -> list[DatabaseInfo]:
        """Último snapshot de cada base (por instancia y `database_ref`)."""
        d = InstanceDatabaseModel
        stmt = (
            select(d)
            .where(d.client_id == client_id)
            .order_by(d.snapshot_date.desc(), d.occurred_at.desc())
        )
        seen: set[tuple[UUID, UUID]] = set()
        out: list[DatabaseInfo] = []
        for row in (await self._s.execute(stmt)).scalars():
            key = (row.instance_id, row.database_ref)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                DatabaseInfo(
                    database_ref=row.database_ref,
                    code=row.code,
                    name=row.name,
                    is_active=row.is_active,
                    is_usable=row.is_usable,
                    credentials_unreadable=row.credentials_unreadable,
                    last_connection_ok_at=_utc(row.last_connection_ok_at)
                    if row.last_connection_ok_at
                    else None,
                    snapshot_date=row.snapshot_date,
                )
            )
        return sorted(out, key=lambda i: i.name.lower())

    async def client_metrics(self, client_id: UUID, period: Period) -> ClientMetrics:
        return ClientMetrics(
            totals=await self.totals(client_id, period),
            series=await self.series(client_id, period),
            by_model=await self.by_model(client_id, period),
            by_database=await self.by_database(client_id, period),
            tools=await self.tools(client_id, period),
            finish_reasons=await self.finish_reasons(client_id, period),
        )


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
