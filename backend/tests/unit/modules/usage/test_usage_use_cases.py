"""Tests de los use cases de consumo.

Son orquestadores delgados sobre el repositorio: validamos que arman el
DTO correcto, que propagan el período sin tocarlo y que el scope de
usuario llega al repo. La lógica SQL real (agregación) se cubre con un
test de integración aparte contra Postgres.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.modules.usage.application.use_cases import (
    GetSystemUsageUseCase,
    GetUserUsageUseCase,
)
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.domain.value_objects import (
    DailyUsage,
    UsagePeriod,
    UsageTotals,
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


class _FakeUsageRepo(UsageRepository):
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def totals_for_user(self, user_id: int, period: UsagePeriod) -> UsageTotals:
        self.calls.append(("totals_for_user", (user_id, period)))
        return _TOTALS

    async def daily_for_user(
        self, user_id: int, period: UsagePeriod
    ) -> list[DailyUsage]:
        self.calls.append(("daily_for_user", (user_id, period)))
        return [DailyUsage(day=date(2026, 5, 15), totals=_TOTALS)]

    async def system_totals(self, period: UsagePeriod) -> UsageTotals:
        self.calls.append(("system_totals", period))
        return _TOTALS

    async def per_user(self, period: UsagePeriod) -> list[UserUsage]:
        self.calls.append(("per_user", period))
        return [
            UserUsage(user_id=7, totals=_TOTALS),
            UserUsage(user_id=None, totals=_TOTALS),
        ]

    async def daily_system(self, period: UsagePeriod) -> list[DailyUsage]:
        self.calls.append(("daily_system", period))
        return [DailyUsage(day=date(2026, 5, 15), totals=_TOTALS)]


@pytest.mark.asyncio
async def test_user_usage_arma_reporte_con_totales_y_serie() -> None:
    repo = _FakeUsageRepo()
    use_case = GetUserUsageUseCase(repo)

    report = await use_case.execute(user_id=42, period=_PERIOD)

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

    await use_case.execute(user_id=99, period=_PERIOD)

    # Ambas consultas reciben el mismo user_id y período.
    assert ("totals_for_user", (99, _PERIOD)) in repo.calls
    assert ("daily_for_user", (99, _PERIOD)) in repo.calls


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
