"""Lectura administrativa del feedback: panel, resumen y export.

Todo se acota a `owner_erp_database_id` (la base con la que iniciaron sesión
quienes calificaron): el administrador de una empresa no ve las
calificaciones de otra. Nunca se devuelven entradas de herramientas ni SQL:
de `tool_invocations` solo se extraen los NOMBRES.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.modules.conversations.infrastructure.persistence.models import (
    ConversationModel,
    MessageModel,
)
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel
from app.modules.feedback.domain.interfaces import FeedbackReportRepository
from app.modules.feedback.domain.value_objects import (
    ANSWER_MAX_CHARS,
    QUESTION_MAX_CHARS,
    DailyFeedback,
    FeedbackFilters,
    FeedbackPage,
    FeedbackRating,
    FeedbackReason,
    FeedbackReportItem,
    FeedbackSummary,
    ModelFeedback,
    ReasonCount,
)
from app.modules.feedback.infrastructure.persistence.models import MessageFeedbackModel

_Fb = MessageFeedbackModel
_TOP_REASONS = 5


def _like_pattern(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _as_day(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _tool_names(raw: Any) -> tuple[str, ...]:
    """Solo los nombres, sin repetir y en orden de uso. Nada de `input`."""
    if not isinstance(raw, list):
        return ()
    names: list[str] = []
    entries: list[Any] = raw  # pyright: ignore[reportUnknownVariableType]
    for entry in entries:
        if isinstance(entry, dict):
            name = cast(Any, entry).get("name")
            if isinstance(name, str) and name and name not in names:
                names.append(name)
    return tuple(names)


class SqlAlchemyFeedbackReportRepository(FeedbackReportRepository):
    def __init__(self, session: AsyncSession, *, reporting_timezone: str):
        self._session = session
        self._tz = reporting_timezone

    # ── Predicados ────────────────────────────────────────────────────────

    @staticmethod
    def _conditions(owner: UUID, filters: FeedbackFilters) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [_Fb.owner_erp_database_id == owner]
        if filters.rating is not None:
            conditions.append(_Fb.rating == filters.rating.value)
        if filters.reason is not None:
            conditions.append(_Fb.reason == filters.reason.value)
        if filters.start is not None:
            conditions.append(_Fb.created_at >= filters.start)
        if filters.end is not None:
            conditions.append(_Fb.created_at < filters.end)
        if filters.provider:
            conditions.append(MessageModel.provider == filters.provider)
        if filters.model:
            conditions.append(MessageModel.model == filters.model)
        if filters.user:
            conditions.append(_Fb.user_login.ilike(_like_pattern(filters.user), escape="\\"))
        if filters.text:
            conditions.append(_Fb.comment.ilike(_like_pattern(filters.text), escape="\\"))
        return conditions

    @staticmethod
    def _joined(stmt: Select[Any]) -> Select[Any]:
        return stmt.select_from(_Fb).join(MessageModel, _Fb.message_id == MessageModel.id)

    def _day_bucket(self) -> ColumnElement[Any]:
        if self._session.get_bind().dialect.name != "sqlite":
            return func.date(func.timezone(self._tz, _Fb.created_at))
        # SQLite no conoce la base de zonas horarias: se corre por el offset
        # vigente (exacto para Colombia, UTC-5 fijo). Igual que `usage`.
        offset = ZoneInfo(self._tz).utcoffset(datetime.now(UTC))
        minutes = int(offset.total_seconds() // 60) if offset else 0
        return func.date(_Fb.created_at, f"{minutes} minutes")

    # ── Listado / export ──────────────────────────────────────────────────

    def _items_statement(self, owner: UUID, filters: FeedbackFilters) -> Select[Any]:
        previous_user = aliased(MessageModel)
        # La pregunta es el mensaje del usuario inmediatamente anterior a la
        # respuesta (no solo el activo: una respuesta reemplazada también se
        # calificó, y su pregunta puede haber sido editada después).
        question = (
            select(func.substr(previous_user.content, 1, QUESTION_MAX_CHARS))
            .where(
                previous_user.conversation_id == MessageModel.conversation_id,
                previous_user.role == "user",
                previous_user.created_at <= MessageModel.created_at,
            )
            .order_by(previous_user.created_at.desc())
            .limit(1)
            .correlate(MessageModel)
            .scalar_subquery()
        )
        stmt = (
            select(
                _Fb.id,
                _Fb.rating,
                _Fb.reason,
                _Fb.comment,
                _Fb.created_at,
                _Fb.updated_at,
                _Fb.user_id,
                _Fb.user_login,
                _Fb.user_name,
                MessageModel.conversation_id,
                MessageModel.id.label("message_id"),
                question.label("question"),
                func.substr(MessageModel.content, 1, ANSWER_MAX_CHARS).label("answer"),
                MessageModel.provider,
                MessageModel.model,
                MessageModel.cost_usd,
                MessageModel.tool_invocations,
                ErpDatabaseModel.code.label("database_code"),
            )
            .select_from(_Fb)
            .join(MessageModel, _Fb.message_id == MessageModel.id)
            .join(ConversationModel, MessageModel.conversation_id == ConversationModel.id)
            .outerjoin(ErpDatabaseModel, ConversationModel.erp_database_id == ErpDatabaseModel.id)
            .where(and_(*self._conditions(owner, filters)))
            .order_by(_Fb.created_at.desc(), _Fb.id)
        )
        return stmt

    @staticmethod
    def _to_item(row: Any) -> FeedbackReportItem:
        return FeedbackReportItem(
            id=str(row.id),
            rating=FeedbackRating(row.rating),
            reason=FeedbackReason(row.reason) if row.reason else None,
            comment=row.comment,
            created_at=row.created_at,
            updated_at=row.updated_at,
            user_id=row.user_id,
            user_login=row.user_login,
            user_name=row.user_name,
            conversation_id=str(row.conversation_id),
            message_id=str(row.message_id),
            question=row.question,
            answer=row.answer or "",
            provider=row.provider,
            model=row.model,
            cost_usd=float(row.cost_usd) if row.cost_usd is not None else None,
            tools=_tool_names(row.tool_invocations),
            database_code=row.database_code,
        )

    async def list_feedback(
        self,
        *,
        owner_erp_database_id: UUID,
        filters: FeedbackFilters,
        limit: int,
        offset: int,
    ) -> FeedbackPage:
        count_stmt = self._joined(select(func.count(_Fb.id))).where(
            and_(*self._conditions(owner_erp_database_id, filters))
        )
        total = int((await self._session.execute(count_stmt)).scalar_one())
        stmt = self._items_statement(owner_erp_database_id, filters).limit(limit).offset(offset)
        rows = (await self._session.execute(stmt)).all()
        return FeedbackPage(
            items=[self._to_item(r) for r in rows], total=total, limit=limit, offset=offset
        )

    async def export_rows(
        self,
        *,
        owner_erp_database_id: UUID,
        filters: FeedbackFilters,
        max_rows: int,
    ) -> list[FeedbackReportItem]:
        stmt = self._items_statement(owner_erp_database_id, filters).limit(max_rows)
        rows = (await self._session.execute(stmt)).all()
        return [self._to_item(r) for r in rows]

    # ── Resumen ───────────────────────────────────────────────────────────

    async def summary(
        self,
        *,
        owner_erp_database_id: UUID,
        filters: FeedbackFilters,
    ) -> FeedbackSummary:
        where = and_(*self._conditions(owner_erp_database_id, filters))

        day = self._day_bucket().label("day")
        daily_rows = (
            await self._session.execute(
                self._joined(select(day, _Fb.rating, func.count(_Fb.id).label("n")))
                .where(where)
                .group_by(day, _Fb.rating)
                .order_by(day)
            )
        ).all()
        per_day: dict[str, dict[str, int]] = defaultdict(lambda: {"up": 0, "down": 0})
        for row in daily_rows:
            per_day[_as_day(row.day)][row.rating] += int(row.n)
        daily = [
            DailyFeedback(day=d, up=v["up"], down=v["down"]) for d, v in sorted(per_day.items())
        ]

        up = sum(d.up for d in daily)
        down = sum(d.down for d in daily)
        total = up + down

        reason_count = func.count(_Fb.id).label("n")
        reason_rows = (
            await self._session.execute(
                self._joined(select(_Fb.reason, reason_count))
                .where(and_(where, _Fb.reason.is_not(None)))
                .group_by(_Fb.reason)
                .order_by(reason_count.desc(), _Fb.reason)
                .limit(_TOP_REASONS)
            )
        ).all()
        top_reasons = [
            ReasonCount(reason=FeedbackReason(r.reason), count=int(r.n)) for r in reason_rows
        ]

        model_rows = (
            await self._session.execute(
                self._joined(
                    select(
                        MessageModel.provider,
                        MessageModel.model,
                        _Fb.rating,
                        func.count(_Fb.id).label("n"),
                    )
                )
                .where(where)
                .group_by(MessageModel.provider, MessageModel.model, _Fb.rating)
            )
        ).all()
        per_model: dict[tuple[str | None, str | None], dict[str, int]] = defaultdict(
            lambda: {"up": 0, "down": 0}
        )
        for row in model_rows:
            per_model[(row.provider, row.model)][row.rating] += int(row.n)
        by_model = sorted(
            (
                ModelFeedback(provider=p, model=m, up=v["up"], down=v["down"])
                for (p, m), v in per_model.items()
            ),
            key=lambda x: (-(x.up + x.down), x.provider or "", x.model or ""),
        )

        return FeedbackSummary(
            total=total,
            up=up,
            down=down,
            positive_pct=round(up * 100 / total, 1) if total else None,
            daily=daily,
            top_reasons=top_reasons,
            by_model=by_model,
        )
