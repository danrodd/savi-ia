"""Tests de los use cases de consumo.

Son orquestadores delgados sobre el repositorio: validamos que arman el
DTO correcto, que propagan el período sin tocarlo y que el scope de
usuario llega al repo. La lógica SQL real (agregación) se cubre con un
test de integración aparte contra Postgres.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.modules.usage.application.use_cases import (
    GetSystemUsageUseCase,
    GetUserUsageUseCase,
)
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.domain.value_objects import (
    ConversationStats,
    ConversationUsage,
    DailyUsage,
    UsageFilters,
    UsagePeriod,
    UsageTotals,
    UserStats,
    UserUsage,
)

_PERIOD = UsagePeriod(
    start=datetime(2026, 5, 1, tzinfo=UTC),
    end=datetime(2026, 6, 1, tzinfo=UTC),
)

_TOTALS = UsageTotals(
    input_tokens=100,
    output_tokens=50,
    cache_read_input_tokens=20,
    cache_creation_input_tokens=5,
    cost_usd=Decimal("0.0125"),
    message_count=3,
)


_DATABASE_A = UUID("11111111-1111-1111-1111-111111111111")


class _FakeUsageRepo(UsageRepository):
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def totals_for_user(
        self,
        user_id: int,
        period: UsagePeriod,
        *,
        erp_database_id: UUID,
        filters: UsageFilters | None = None,
    ) -> UsageTotals:
        self.calls.append(("totals_for_user", (user_id, period, erp_database_id, filters)))
        return _TOTALS

    async def daily_for_user(
        self,
        user_id: int,
        period: UsagePeriod,
        *,
        erp_database_id: UUID,
        filters: UsageFilters | None = None,
    ) -> list[DailyUsage]:
        self.calls.append(("daily_for_user", (user_id, period, erp_database_id, filters)))
        return [DailyUsage(day=date(2026, 5, 15), totals=_TOTALS)]

    async def system_totals(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> UsageTotals:
        self.calls.append(("system_totals", (period, filters)))
        return _TOTALS

    async def per_user(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> list[UserUsage]:
        self.calls.append(("per_user", (period, filters)))
        return [
            UserUsage(user_id=7, totals=_TOTALS),
            UserUsage(user_id=None, totals=_TOTALS),
        ]

    async def daily_system(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> list[DailyUsage]:
        self.calls.append(("daily_system", (period, filters)))
        return [DailyUsage(day=date(2026, 5, 15), totals=_TOTALS)]

    async def conversation_stats(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> ConversationStats:
        self.calls.append(("conversation_stats", (period, filters)))
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

    async def user_stats(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> UserStats:
        self.calls.append(("user_stats", (period, filters)))
        return UserStats(active_count=0, avg_cost_usd=0.0, avg_conversations=0.0)

    async def per_conversation(
        self,
        period: UsagePeriod,
        *,
        limit: int,
        filters: UsageFilters | None = None,
    ) -> list[ConversationUsage]:
        self.calls.append(("per_conversation", (period, limit, filters)))
        return []


@pytest.mark.asyncio
async def test_user_usage_arma_reporte_con_totales_y_serie() -> None:
    repo = _FakeUsageRepo()
    use_case = GetUserUsageUseCase(repo)

    report = await use_case.execute(user_id=42, period=_PERIOD, erp_database_id=_DATABASE_A)

    assert report.user_id == 42
    assert report.period_start == _PERIOD.start
    assert report.period_end == _PERIOD.end
    assert report.totals == _TOTALS
    assert len(report.daily) == 1
    assert report.daily[0].day == date(2026, 5, 15)


@pytest.mark.asyncio
async def test_user_usage_propaga_scope_de_usuario_al_repo() -> None:
    repo = _FakeUsageRepo()
    use_case = GetUserUsageUseCase(repo)

    await use_case.execute(user_id=99, period=_PERIOD, erp_database_id=_DATABASE_A)

    # Ambas consultas reciben el mismo user_id, período y base. La base no
    # es opcional: sin ella el consumo del usuario 99 sumaría el de todos
    # los usuarios 99 de los demás clientes.
    assert ("totals_for_user", (99, _PERIOD, _DATABASE_A, None)) in repo.calls
    assert ("daily_for_user", (99, _PERIOD, _DATABASE_A, None)) in repo.calls


@pytest.mark.asyncio
async def test_user_usage_propaga_filtros() -> None:
    repo = _FakeUsageRepo()
    use_case = GetUserUsageUseCase(repo)
    filters = UsageFilters(provider="Claude", model=" claude-sonnet ")

    await use_case.execute(
        user_id=99,
        period=_PERIOD,
        erp_database_id=_DATABASE_A,
        filters=filters,
    )

    assert ("totals_for_user", (99, _PERIOD, _DATABASE_A, filters)) in repo.calls
    assert ("daily_for_user", (99, _PERIOD, _DATABASE_A, filters)) in repo.calls


@pytest.mark.asyncio
async def test_total_tokens_suma_las_cuatro_categorias() -> None:
    # input(100) + output(50) + cache_read(20) + cache_creation(5) = 175
    assert _TOTALS.total_tokens == 175


@pytest.mark.asyncio
async def test_system_usage_arma_reporte_global() -> None:
    repo = _FakeUsageRepo()
    use_case = GetSystemUsageUseCase(repo)

    report = await use_case.execute(period=_PERIOD)

    assert report.totals == _TOTALS
    assert len(report.per_user) == 2
    assert report.per_user[0].user_id == 7
    # El usuario legado (None) sigue contando.
    assert report.per_user[1].user_id is None
    assert len(report.daily) == 1


@pytest.mark.asyncio
async def test_system_usage_no_filtra_por_usuario() -> None:
    repo = _FakeUsageRepo()
    use_case = GetSystemUsageUseCase(repo)

    await use_case.execute(period=_PERIOD)

    called = {name for name, _ in repo.calls}
    assert called == {"system_totals", "per_user", "daily_system"}
