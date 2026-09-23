"""Tests del use case de KPIs.

Foco en las DERIVACIONES de negocio (costo por turno, costo por día,
proyección mensual, ratio de caché), que es donde está la lógica. Los
agregados crudos vienen del repo (mockeado). La parte SQL (percentiles)
se cubre en integración contra Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.modules.usage.application.use_cases import GetUsageKpisUseCase
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.domain.value_objects import (
    ConversationStats,
    ConversationUsage,
    DailyProviderUsage,
    DailyUsage,
    DatabaseUsage,
    DocumentReadingUsage,
    ProviderUsage,
    UsageFilters,
    UsagePeriod,
    UsageTotals,
    UserStats,
    UserUsage,
)

# 10 días de período para que la proyección mensual sea fácil de verificar.
_PERIOD = UsagePeriod(
    start=datetime(2026, 5, 1, tzinfo=UTC),
    end=datetime(2026, 5, 11, tzinfo=UTC),
)

_TOTALS = UsageTotals(
    input_tokens=600,
    output_tokens=200,
    cache_read_input_tokens=300,
    cache_creation_input_tokens=100,
    cost_usd=Decimal("10.00"),
    message_count=40,
)

_CONV_STATS = ConversationStats(
    count=8,
    avg_cost_usd=1.25,
    p50_cost_usd=0.9,
    p90_cost_usd=3.0,
    p95_cost_usd=4.0,
    max_cost_usd=5.0,
    avg_tokens=150.0,
    avg_turns=5.0,
)

_USER_STATS = UserStats(active_count=4, avg_cost_usd=2.5, avg_conversations=2.0)


class _FakeRepo(UsageRepository):
    async def totals_for_user(
        self,
        user_id: int,
        period: UsagePeriod,
        *,
        erp_database_id: UUID,
        filters: UsageFilters | None = None,
    ) -> UsageTotals:  # noqa: ARG002
        return _TOTALS

    async def daily_for_user(
        self,
        user_id: int,
        period: UsagePeriod,
        *,
        erp_database_id: UUID,
        filters: UsageFilters | None = None,
    ) -> list[DailyUsage]:  # noqa: ARG002
        return []

    async def provider_totals_for_user(
        self,
        user_id: int,
        period: UsagePeriod,
        *,
        erp_database_id: UUID,
        filters: UsageFilters | None = None,
    ) -> list[ProviderUsage]:  # noqa: ARG002
        return []

    async def daily_provider_for_user(
        self,
        user_id: int,
        period: UsagePeriod,
        *,
        erp_database_id: UUID,
        filters: UsageFilters | None = None,
    ) -> list[DailyProviderUsage]:  # noqa: ARG002
        return []

    async def system_totals(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> UsageTotals:  # noqa: ARG002
        return _TOTALS

    async def per_user(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> list[UserUsage]:  # noqa: ARG002
        return []

    async def daily_system(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> list[DailyUsage]:  # noqa: ARG002
        return []

    async def provider_totals_system(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> list[ProviderUsage]:  # noqa: ARG002
        return []

    async def document_reading_system(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> DocumentReadingUsage:
        return DocumentReadingUsage()

    async def database_totals_system(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> list[DatabaseUsage]:  # noqa: ARG002
        return []

    async def daily_provider_system(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> list[DailyProviderUsage]:  # noqa: ARG002
        return []

    async def conversation_stats(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> ConversationStats:  # noqa: ARG002
        return _CONV_STATS

    async def user_stats(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> UserStats:  # noqa: ARG002
        return _USER_STATS

    async def per_conversation(
        self,
        period: UsagePeriod,
        *,
        limit: int,
        filters: UsageFilters | None = None,
    ) -> list[ConversationUsage]:  # noqa: ARG002
        return []


@pytest.mark.asyncio
async def test_kpis_derivan_costo_por_turno_y_tokens() -> None:
    kpis = await GetUsageKpisUseCase(_FakeRepo()).execute(_PERIOD)

    # 10 USD / 40 turnos = 0.25
    assert kpis.avg_cost_per_turn_usd == pytest.approx(0.25)
    # total_tokens 1200 / 40 = 30
    assert kpis.avg_tokens_per_turn == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_kpis_proyeccion_mensual() -> None:
    kpis = await GetUsageKpisUseCase(_FakeRepo()).execute(_PERIOD)

    # 10 USD en 10 días = 1 USD/día → 30 USD/mes
    assert kpis.period_days == 10
    assert kpis.avg_cost_per_day_usd == pytest.approx(1.0)
    assert kpis.projected_monthly_cost_usd == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_kpis_ratio_cache() -> None:
    kpis = await GetUsageKpisUseCase(_FakeRepo()).execute(_PERIOD)

    # cache_read 300 / (input 600 + cache_read 300 + cache_creation 100) = 0.3
    assert kpis.cache_read_ratio == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_kpis_pasan_percentiles_de_conversacion() -> None:
    kpis = await GetUsageKpisUseCase(_FakeRepo()).execute(_PERIOD)

    assert kpis.conversations.p95_cost_usd == 4.0
    assert kpis.users.active_count == 4


@pytest.mark.asyncio
async def test_kpis_sin_turnos_no_divide_por_cero() -> None:
    class _EmptyRepo(_FakeRepo):
        async def system_totals(
            self, period: UsagePeriod, *, filters: UsageFilters | None = None
        ) -> UsageTotals:  # noqa: ARG002
            return UsageTotals()

    kpis = await GetUsageKpisUseCase(_EmptyRepo()).execute(_PERIOD)

    assert kpis.avg_cost_per_turn_usd == 0.0
    assert kpis.avg_tokens_per_turn == 0.0
    assert kpis.cache_read_ratio == 0.0
