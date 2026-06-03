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

from decimal import Decimal
from typing import Any

from sqlalchemy import Integer, RowMapping, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modules.conversations.infrastructure.persistence.models.conversation_model import (
    ConversationModel,
    MessageModel,
)
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.domain.value_objects import (
    DailyUsage,
    UsagePeriod,
    UsageTotals,
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


def _count() -> ColumnElement[Any]:
    return func.count(MessageModel.id)


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

    def _day_bucket(self) -> ColumnElement[Any]:
        """Fecha local (en la zona de reporte) del turno, para agrupar."""
        return func.date(func.timezone(self._tz, MessageModel.created_at))

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
            DailyUsage(day=row["day"], totals=_row_to_totals(row)) for row in rows
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
