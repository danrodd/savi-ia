"""Repositorio de consumo (Opción A: agregación on-demand).

No hay tablas nuevas: se agrega directo sobre `messages` (join con
`conversations` para resolver el `user_id`). El dato fuente son las
columnas `usage` (JSONB) y `cost_usd` (Numeric) que el módulo `chat`
ya persiste por cada turno del asistente.

Decisión de medición: se cuentan TODOS los turnos del asistente que
tienen costo — incluidos los de conversaciones borradas y los mensajes
`superseded` (editados/regenerados). Esos tokens se pagaron; para medir
gasto real esa es la cifra correcta.
"""

import math
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, RowMapping, Select, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modules.conversations.infrastructure.persistence.models.conversation_model import (
    ConversationModel,
    MessageModel,
)
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.domain.value_objects import (
    ConversationStats,
    ConversationUsage,
    DailyUsage,
    UsagePeriod,
    UsageTotals,
    UserStats,
    UserUsage,
)

_ASSISTANT_ROLE = "assistant"


def _token_sum(field: str) -> ColumnElement[Any]:
    """Suma un campo entero del JSONB `usage` (NULL → 0).

    Usa el operador `->>` (texto) + cast a Integer en vez de `.astext`
    para mantener el tipado limpio bajo Pyright strict.
    """
    return func.coalesce(
        func.sum(cast(MessageModel.usage.op("->>")(field), Integer)), 0
    )


def _cost_sum() -> ColumnElement[Any]:
    return func.coalesce(func.sum(MessageModel.cost_usd), Decimal("0"))


def _total_tokens_sum() -> ColumnElement[Any]:
    """Suma de las cuatro categorías de tokens en una sola expresión."""
    return (
        _token_sum("input_tokens")
        + _token_sum("output_tokens")
        + _token_sum("cache_read_input_tokens")
        + _token_sum("cache_creation_input_tokens")
    )


def _count() -> ColumnElement[Any]:
    return func.count(MessageModel.id)


def _as_date(value: Any) -> date:
    """Normaliza el bucket de día a `date`.

    Postgres devuelve un `date`; SQLite devuelve el texto `YYYY-MM-DD`.
    `DailyUsage.day` está tipado `date` y es un dataclass frozen (no
    coerciona), así que sin esto la API serviría un tipo distinto según
    el motor.
    """
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _percentile_cont(sorted_values: list[float], quantile: float) -> float:
    """Equivalente en Python de `percentile_cont` de Postgres.

    SQLite no tiene agregados ordenados. Misma interpolación lineal que
    Postgres para que las cifras del dashboard no cambien según el motor.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = quantile * (len(sorted_values) - 1)
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return sorted_values[low]
    weight = position - low
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * weight


# Orden fijo de columnas agregadas — `_row_to_totals` lee por nombre de
# label, así que el orden solo importa para legibilidad.
def _totals_columns() -> tuple[ColumnElement[Any], ...]:
    return (
        _token_sum("input_tokens").label("input_tokens"),
        _token_sum("output_tokens").label("output_tokens"),
        _token_sum("cache_read_input_tokens").label("cache_read_input_tokens"),
        _token_sum("cache_creation_input_tokens").label("cache_creation_input_tokens"),
        _cost_sum().label("cost_usd"),
        _count().label("message_count"),
    )


def _row_to_totals(m: RowMapping) -> UsageTotals:
    return UsageTotals(
        input_tokens=int(m["input_tokens"]),
        output_tokens=int(m["output_tokens"]),
        cache_read_input_tokens=int(m["cache_read_input_tokens"]),
        cache_creation_input_tokens=int(m["cache_creation_input_tokens"]),
        cost_usd=Decimal(m["cost_usd"]),
        message_count=int(m["message_count"]),
    )


class SqlAlchemyUsageRepository(UsageRepository):
    def __init__(self, session: AsyncSession, *, reporting_timezone: str):
        self._session = session
        self._tz = reporting_timezone

    @property
    def _is_sqlite(self) -> bool:
        """SQLite es el motor de la instalación de escritorio.

        Le faltan `timezone()` y los agregados ordenados
        (`percentile_cont`), así que esas dos operaciones se resuelven por
        otro camino.
        """
        return self._session.get_bind().dialect.name == "sqlite"

    def _day_bucket(self) -> ColumnElement[Any]:
        """Fecha local (en la zona de reporte) del turno, para agrupar."""
        if not self._is_sqlite:
            return func.date(func.timezone(self._tz, MessageModel.created_at))
        # ponytail: SQLite no conoce la base de datos de zonas horarias, así
        # que desplazamos por el offset vigente hoy. Exacto para Colombia
        # (UTC-5 fijo, sin horario de verano). Si algún día se reporta en
        # una zona con DST, los turnos del otro semestre caen una hora
        # corridos: ahí toca bucketear en Python o subir a Postgres.
        offset = ZoneInfo(self._tz).utcoffset(datetime.now(UTC))
        minutes = int(offset.total_seconds() // 60) if offset else 0
        return func.date(MessageModel.created_at, f"{minutes} minutes")

    def _scoped(
        self, period: UsagePeriod, *, user_id: int | None
    ) -> ColumnElement[bool]:
        """Predicado común: turnos del asistente dentro del período."""
        conditions: list[ColumnElement[bool]] = [
            MessageModel.role == _ASSISTANT_ROLE,
            MessageModel.created_at >= period.start,
            MessageModel.created_at < period.end,
        ]
        if user_id is not None:
            conditions.append(ConversationModel.user_id == user_id)
        return and_(*conditions)

    async def _totals(
        self, period: UsagePeriod, *, user_id: int | None
    ) -> UsageTotals:
        stmt = (
            select(*_totals_columns())
            .select_from(MessageModel)
            .join(ConversationModel, MessageModel.conversation_id == ConversationModel.id)
            .where(self._scoped(period, user_id=user_id))
        )
        row = (await self._session.execute(stmt)).mappings().one()
        return _row_to_totals(row)

    async def _daily(
        self, period: UsagePeriod, *, user_id: int | None
    ) -> list[DailyUsage]:
        day = self._day_bucket().label("day")
        stmt = (
            select(day, *_totals_columns())
            .select_from(MessageModel)
            .join(ConversationModel, MessageModel.conversation_id == ConversationModel.id)
            .where(self._scoped(period, user_id=user_id))
            .group_by(day)
            .order_by(day)
        )
        rows = (await self._session.execute(stmt)).mappings().all()
        return [
            DailyUsage(day=_as_date(row["day"]), totals=_row_to_totals(row))
            for row in rows
        ]

    async def totals_for_user(
        self, user_id: int, period: UsagePeriod
    ) -> UsageTotals:
        return await self._totals(period, user_id=user_id)

    async def daily_for_user(
        self, user_id: int, period: UsagePeriod
    ) -> list[DailyUsage]:
        return await self._daily(period, user_id=user_id)

    async def system_totals(self, period: UsagePeriod) -> UsageTotals:
        return await self._totals(period, user_id=None)

    async def daily_system(self, period: UsagePeriod) -> list[DailyUsage]:
        return await self._daily(period, user_id=None)

    async def per_user(self, period: UsagePeriod) -> list[UserUsage]:
        uid = ConversationModel.user_id.label("user_id")
        cost = _cost_sum().label("cost_usd")
        stmt = (
            select(uid, *_totals_columns())
            .select_from(MessageModel)
            .join(ConversationModel, MessageModel.conversation_id == ConversationModel.id)
            .where(self._scoped(period, user_id=None))
            .group_by(uid)
            # Ranking: el que más gastó primero.
            .order_by(cost.desc())
        )
        rows = (await self._session.execute(stmt)).mappings().all()
        return [
            UserUsage(user_id=row["user_id"], totals=_row_to_totals(row))
            for row in rows
        ]

    def _per_conversation_aggregate(self, period: UsagePeriod) -> Select[Any]:
        """Costo/tokens/turnos por conversación. Portable a los dos motores."""
        return (
            select(
                func.coalesce(func.sum(MessageModel.cost_usd), Decimal("0")).label("cost"),
                _total_tokens_sum().label("tokens"),
                func.count(MessageModel.id).label("turns"),
            )
            .select_from(MessageModel)
            .join(ConversationModel, MessageModel.conversation_id == ConversationModel.id)
            .where(self._scoped(period, user_id=None))
            .group_by(ConversationModel.id)
        )

    async def _conversation_stats_in_python(self, base: Select[Any]) -> ConversationStats:
        """Percentiles fuera de la BD, para SQLite.

        Trae una fila por conversación del período. En una instalación de
        escritorio son decenas o cientos de filas: traerlas es más barato
        que sostener dos dialectos de SQL.
        """
        rows = (await self._session.execute(base)).mappings().all()
        if not rows:
            return ConversationStats(
                count=0,
                avg_cost_usd=0.0,
                p50_cost_usd=0.0,
                p90_cost_usd=0.0,
                p95_cost_usd=0.0,
                max_cost_usd=0.0,
                avg_tokens=0.0,
                avg_turns=0.0,
            )
        costs = sorted(float(row["cost"]) for row in rows)
        tokens = [float(row["tokens"]) for row in rows]
        turns = [float(row["turns"]) for row in rows]
        return ConversationStats(
            count=len(rows),
            avg_cost_usd=sum(costs) / len(costs),
            p50_cost_usd=_percentile_cont(costs, 0.5),
            p90_cost_usd=_percentile_cont(costs, 0.9),
            p95_cost_usd=_percentile_cont(costs, 0.95),
            max_cost_usd=costs[-1],
            avg_tokens=sum(tokens) / len(tokens),
            avg_turns=sum(turns) / len(turns),
        )

    async def conversation_stats(self, period: UsagePeriod) -> ConversationStats:
        base = self._per_conversation_aggregate(period)
        if self._is_sqlite:
            return await self._conversation_stats_in_python(base)

        per_conv = base.subquery()
        cost = per_conv.c.cost
        # Paso 2: percentiles + promedios sobre el costo por conversación.
        # percentile_cont los calcula Postgres nativo (interpolación lineal).
        stmt = select(
            func.count().label("count"),
            func.coalesce(func.avg(cost), 0).label("avg_cost"),
            func.coalesce(func.percentile_cont(0.5).within_group(cost), 0).label("p50"),
            func.coalesce(func.percentile_cont(0.9).within_group(cost), 0).label("p90"),
            func.coalesce(func.percentile_cont(0.95).within_group(cost), 0).label("p95"),
            func.coalesce(func.max(cost), 0).label("max_cost"),
            func.coalesce(func.avg(per_conv.c.tokens), 0).label("avg_tokens"),
            func.coalesce(func.avg(per_conv.c.turns), 0).label("avg_turns"),
        )
        m = (await self._session.execute(stmt)).mappings().one()
        return ConversationStats(
            count=int(m["count"]),
            avg_cost_usd=float(m["avg_cost"]),
            p50_cost_usd=float(m["p50"]),
            p90_cost_usd=float(m["p90"]),
            p95_cost_usd=float(m["p95"]),
            max_cost_usd=float(m["max_cost"]),
            avg_tokens=float(m["avg_tokens"]),
            avg_turns=float(m["avg_turns"]),
        )

    async def user_stats(self, period: UsagePeriod) -> UserStats:
        # Excluye conversaciones legadas (user_id NULL): no son usuarios
        # facturables reales.
        per_user = (
            select(
                ConversationModel.user_id.label("uid"),
                func.coalesce(func.sum(MessageModel.cost_usd), Decimal("0")).label("cost"),
                func.count(func.distinct(ConversationModel.id)).label("convs"),
            )
            .select_from(MessageModel)
            .join(ConversationModel, MessageModel.conversation_id == ConversationModel.id)
            .where(
                and_(
                    self._scoped(period, user_id=None),
                    ConversationModel.user_id.is_not(None),
                )
            )
            .group_by(ConversationModel.user_id)
            .subquery()
        )
        stmt = select(
            func.count().label("active"),
            func.coalesce(func.avg(per_user.c.cost), 0).label("avg_cost"),
            func.coalesce(func.avg(per_user.c.convs), 0).label("avg_convs"),
        )
        m = (await self._session.execute(stmt)).mappings().one()
        return UserStats(
            active_count=int(m["active"]),
            avg_cost_usd=float(m["avg_cost"]),
            avg_conversations=float(m["avg_convs"]),
        )

    async def per_conversation(
        self, period: UsagePeriod, *, limit: int
    ) -> list[ConversationUsage]:
        cost = func.coalesce(func.sum(MessageModel.cost_usd), Decimal("0")).label(
            "cost_usd"
        )
        stmt = (
            select(
                ConversationModel.id.label("conversation_id"),
                ConversationModel.user_id.label("user_id"),
                ConversationModel.title.label("title"),
                func.count(MessageModel.id).label("turns"),
                _total_tokens_sum().label("total_tokens"),
                cost,
                func.max(MessageModel.created_at).label("last_activity"),
            )
            .select_from(MessageModel)
            .join(ConversationModel, MessageModel.conversation_id == ConversationModel.id)
            .where(self._scoped(period, user_id=None))
            .group_by(
                ConversationModel.id,
                ConversationModel.user_id,
                ConversationModel.title,
            )
            .order_by(cost.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).mappings().all()
        return [
            ConversationUsage(
                conversation_id=row["conversation_id"],
                user_id=row["user_id"],
                title=row["title"],
                turns=int(row["turns"]),
                total_tokens=int(row["total_tokens"]),
                cost_usd=float(row["cost_usd"]),
                last_activity=row["last_activity"],
            )
            for row in rows
        ]
