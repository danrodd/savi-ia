"""Carga del contexto de evaluación y tarea periódica del motor de alertas (§5.2)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.modules.alerts.application import (
    EvaluateAlertsUseCase,
    EvaluationResult,
    NoopAlertNotifier,
)
from app.modules.alerts.infrastructure import (
    SqlAlchemyAlertRepository,
    SqlAlchemyAlertRuleRepository,
)
from app.modules.alerts.rules import DayStats, EvalContext
from app.modules.clients.infrastructure import ClientModel
from app.modules.clients.infrastructure import to_entity as client_entity
from app.modules.ingest.infrastructure import EvTurnModel
from app.modules.instances.infrastructure import InstanceModel
from app.modules.instances.infrastructure import to_entity as instance_entity
from app.modules.metrics.definitions import ERROR_FINISH_REASON
from app.modules.metrics.queries import BOGOTA
from app.shared.clock import Clock

logger = logging.getLogger("savi_cloud.alerts")

HISTORY_DAYS = 15  # hoy + los 14 previos que usa `cost_spike`
BOGOTA_OFFSET = timedelta(hours=-5)  # Colombia no tiene horario de verano


def bogota_today(now: datetime) -> date:
    return (now.astimezone(UTC) + BOGOTA_OFFSET).date()


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


async def load_context(session: AsyncSession, settings: Settings, now: datetime) -> EvalContext:
    clients = {
        m.id: client_entity(m) for m in (await session.execute(select(ClientModel))).scalars()
    }
    instances = [
        instance_entity(m) for m in (await session.execute(select(InstanceModel))).scalars()
    ]

    today = bogota_today(now)
    since = datetime.combine(today - timedelta(days=HISTORY_DAYS - 1), datetime.min.time(), UTC)
    since -= BOGOTA_OFFSET  # medianoche de Bogotá expresada en UTC
    if session.get_bind().dialect.name == "postgresql":
        day = cast(func.timezone(BOGOTA, EvTurnModel.occurred_at), Date)
    else:
        day = func.date(EvTurnModel.occurred_at, "-5 hours")
    stmt = (
        select(
            EvTurnModel.client_id,
            day,
            func.count(),
            func.sum(case((EvTurnModel.finish_reason == ERROR_FINISH_REASON, 1), else_=0)),
            func.sum(EvTurnModel.cost_usd),
        )
        .where(EvTurnModel.occurred_at >= since)
        .group_by(EvTurnModel.client_id, day)
    )
    daily: dict[UUID, dict[date, DayStats]] = defaultdict(dict)
    for client_id, d, turns, errors, cost in (await session.execute(stmt)).all():
        daily[client_id][_as_date(d)] = DayStats(
            turns=int(turns),
            errors=int(errors or 0),
            cost_usd=Decimal(str(cost)) if cost is not None else Decimal(0),
        )

    return EvalContext(
        now=now,
        today=today,
        clients=clients,
        instances=instances,
        daily=dict(daily),
        latest_version=settings.latest_version or None,
        latest_published_at=settings.latest_version_published_at,
    )


async def run_evaluation(
    sessionmaker: async_sessionmaker[AsyncSession], settings: Settings, clock: Clock
) -> EvaluationResult:
    """Una evaluación completa en una sola transacción."""
    async with sessionmaker() as session, session.begin():
        now = clock()
        ctx = await load_context(session, settings, now)
        return await EvaluateAlertsUseCase(
            SqlAlchemyAlertRepository(session),
            SqlAlchemyAlertRuleRepository(session),
            NoopAlertNotifier(),
            clock,
        ).execute(ctx)


async def alert_loop(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
    clock: Clock,
    interval_seconds: float,
) -> None:
    """Evalúa cada `interval_seconds`. Un ciclo que falla se registra y no detiene el job."""
    while True:
        try:
            result = await run_evaluation(sessionmaker, settings, clock)
            if result.opened or result.resolved:
                logger.info(
                    "alerts evaluated",
                    extra={
                        "opened": result.opened,
                        "updated": result.updated,
                        "resolved": result.resolved,
                    },
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("alert evaluation failed")
        await asyncio.sleep(interval_seconds)


def start_alert_task(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
    clock: Clock,
) -> asyncio.Task[None] | None:
    if settings.alerts_interval_seconds <= 0:
        return None
    return asyncio.create_task(
        alert_loop(sessionmaker, settings, clock, settings.alerts_interval_seconds)
    )


async def stop_alert_task(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
