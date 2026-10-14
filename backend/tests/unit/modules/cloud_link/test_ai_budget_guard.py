"""Política de IA de Cloud aplicada antes de cada turno (M3).

El guard decide con cuatro cosas: proveedores permitidos, precio disponible para medir, tope
por persona (con excepciones) y tope del proveedor para toda la instalación.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.chat.domain.exceptions import AiAccessDeniedError
from app.modules.chat.domain.interfaces import ActiveProvider, ModelPrice
from app.modules.cloud_link.application.pseudonymizer import PseudonymizerProvider
from app.modules.cloud_link.domain.entities.cloud_link_state import CloudLinkState
from app.modules.cloud_link.domain.value_objects import AiLimits, SyncPolicy
from app.modules.cloud_link.infrastructure.ai_budget_guard import (
    BUDGET_EXCEEDED,
    PRICE_MISSING,
    PROVIDER_NOT_ALLOWED,
    CloudAiBudgetGuard,
    month_period,
)
from app.modules.cloud_link.infrastructure.composition import CloudLinkServices
from app.modules.usage.domain.value_objects import ProviderUsage, UsagePeriod, UsageTotals

from .support import FakeCloudApi

DB = uuid4()
USER_ID = 7


class _FakeUsage:
    """Consumo del mes ya agregado: lo único que el guard le pregunta."""

    def __init__(self) -> None:
        self.user: dict[str, Decimal] = {}
        self.system: dict[str, Decimal] = {}
        self.periods: list[UsagePeriod] = []

    @staticmethod
    def _rows(by_provider: dict[str, Decimal]) -> list[ProviderUsage]:
        return [
            ProviderUsage(provider=p, model="m", totals=UsageTotals(cost_usd=c))
            for p, c in by_provider.items()
        ]

    async def provider_totals_for_user(self, *_: Any, **__: Any) -> list[ProviderUsage]:
        return self._rows(self.user)

    async def provider_totals_system(self, period: UsagePeriod, **_: Any) -> list[ProviderUsage]:
        self.periods.append(period)
        return self._rows(self.system)


@pytest.fixture
def usage() -> _FakeUsage:
    return _FakeUsage()


@pytest.fixture
def services(make_services: Callable[..., CloudLinkServices]) -> CloudLinkServices:
    return make_services(FakeCloudApi())


async def _link(services: CloudLinkServices, ai: AiLimits | None) -> None:
    def mutate(state: CloudLinkState) -> None:
        state.instance_id = uuid4()
        state.secret = "svk_ins_secreto"
        state.policy = SyncPolicy(ai=ai)

    await services.repository.update(mutate)


def _guard(services: CloudLinkServices, usage: _FakeUsage) -> CloudAiBudgetGuard:
    @asynccontextmanager
    async def source() -> AsyncGenerator[_FakeUsage]:
        yield usage

    return CloudAiBudgetGuard(
        services.repository,
        PseudonymizerProvider(services.repository),
        source,  # pyright: ignore[reportArgumentType]
        "America/Bogota",
    )


def _provider(kind: str = "claude", model: str = "claude-sonnet-4-6") -> ActiveProvider:
    return ActiveProvider(
        kind=kind,
        chat_model=model,
        title_model=model,
        credential_kind="api_key",
    )


async def _user_ref(services: CloudLinkServices) -> str:
    return (await PseudonymizerProvider(services.repository).get()).user_ref(DB, USER_ID)


async def _check(guard: CloudAiBudgetGuard, provider: ActiveProvider) -> None:
    await guard.check(user_id=USER_ID, erp_database_id=DB, provider=provider)


async def _code(guard: CloudAiBudgetGuard, provider: ActiveProvider) -> str:
    with pytest.raises(AiAccessDeniedError) as raised:
        await _check(guard, provider)
    return raised.value.error_code


# ── sin límites ───────────────────────────────────────────────────────────────────────────
async def test_not_linked_means_no_limits(services: CloudLinkServices, usage: _FakeUsage) -> None:
    usage.user = {"claude": Decimal("999")}

    await _check(_guard(services, usage), _provider())


async def test_linked_without_ai_policy_means_no_limits(
    services: CloudLinkServices, usage: _FakeUsage
) -> None:
    await _link(services, None)
    usage.user = {"claude": Decimal("999")}

    await _check(_guard(services, usage), _provider())


# ── proveedores permitidos ────────────────────────────────────────────────────────────────
async def test_a_provider_outside_the_allowed_list_is_rejected(
    services: CloudLinkServices, usage: _FakeUsage
) -> None:
    await _link(services, AiLimits(allowed_providers=frozenset({"claude"})))

    code = await _code(_guard(services, usage), _provider("gemini", "gemini-2.5-flash"))

    assert code == PROVIDER_NOT_ALLOWED


async def test_an_allowed_provider_passes(services: CloudLinkServices, usage: _FakeUsage) -> None:
    await _link(services, AiLimits(allowed_providers=frozenset({"claude"})))

    await _check(_guard(services, usage), _provider())


# ── tope por persona ──────────────────────────────────────────────────────────────────────
async def test_user_below_the_cap_passes_and_at_the_cap_is_blocked(
    services: CloudLinkServices, usage: _FakeUsage
) -> None:
    await _link(services, AiLimits(user_monthly_usd=Decimal("5")))
    guard = _guard(services, usage)

    usage.user = {"claude": Decimal("4.99")}
    await _check(guard, _provider())

    usage.user = {"claude": Decimal("5")}
    assert await _code(guard, _provider()) == BUDGET_EXCEEDED


async def test_the_user_cap_adds_up_all_providers(
    services: CloudLinkServices, usage: _FakeUsage
) -> None:
    await _link(services, AiLimits(user_monthly_usd=Decimal("5")))
    usage.user = {"claude": Decimal("3"), "gemini": Decimal("2.5")}

    code = await _code(_guard(services, usage), _provider())

    assert code == BUDGET_EXCEEDED


async def test_a_personal_override_replaces_the_general_cap(
    services: CloudLinkServices, usage: _FakeUsage
) -> None:
    ref = await _user_ref(services)
    await _link(
        services,
        AiLimits(user_monthly_usd=Decimal("5"), user_overrides={ref: Decimal("20")}),
    )
    usage.user = {"claude": Decimal("10")}

    await _check(_guard(services, usage), _provider())


async def test_an_override_of_zero_leaves_the_person_without_ai(
    services: CloudLinkServices, usage: _FakeUsage
) -> None:
    ref = await _user_ref(services)
    await _link(services, AiLimits(user_overrides={ref: Decimal("0")}))

    assert await _code(_guard(services, usage), _provider()) == BUDGET_EXCEEDED


# ── tope del proveedor ────────────────────────────────────────────────────────────────────
async def test_the_provider_pool_blocks_everyone_when_exhausted(
    services: CloudLinkServices, usage: _FakeUsage
) -> None:
    await _link(services, AiLimits(provider_monthly_usd={"gemini": Decimal("50")}))
    provider = ActiveProvider(
        kind="gemini",
        chat_model="gemini-2.5-flash",
        title_model="gemini-2.5-flash",
        credential_kind="api_key",
        pricing={"gemini-2.5-flash": ModelPrice(input=0.1, output=0.4)},
    )
    guard = _guard(services, usage)

    usage.system = {"gemini": Decimal("49.5")}
    await _check(guard, provider)

    usage.system = {"gemini": Decimal("50")}
    assert await _code(guard, provider) == BUDGET_EXCEEDED


async def test_the_provider_pool_does_not_affect_another_provider(
    services: CloudLinkServices, usage: _FakeUsage
) -> None:
    await _link(services, AiLimits(provider_monthly_usd={"gemini": Decimal("50")}))
    usage.system = {"gemini": Decimal("80")}

    await _check(_guard(services, usage), _provider("claude"))


# ── precio ────────────────────────────────────────────────────────────────────────────────
async def test_a_cap_on_a_provider_that_does_not_report_cost_needs_a_price(
    services: CloudLinkServices, usage: _FakeUsage
) -> None:
    await _link(services, AiLimits(user_monthly_usd=Decimal("5")))

    code = await _code(_guard(services, usage), _provider("gemini", "gemini-2.5-flash"))

    assert code == PRICE_MISSING


async def test_claude_reports_its_own_cost_so_it_needs_no_price(
    services: CloudLinkServices, usage: _FakeUsage
) -> None:
    await _link(services, AiLimits(user_monthly_usd=Decimal("5")))

    await _check(_guard(services, usage), _provider("claude"))


async def test_without_any_cap_a_missing_price_does_not_block(
    services: CloudLinkServices, usage: _FakeUsage
) -> None:
    await _link(services, AiLimits(allowed_providers=frozenset({"claude", "gemini"})))

    await _check(_guard(services, usage), _provider("gemini", "gemini-2.5-flash"))


# ── mes ───────────────────────────────────────────────────────────────────────────────────
def test_the_month_is_the_calendar_month_of_the_reporting_timezone() -> None:
    # 1 de noviembre 02:00 UTC todavía es 31 de octubre en Bogotá (UTC-5).
    period = month_period(datetime(2026, 11, 1, 2, 0, tzinfo=UTC), "America/Bogota")

    assert period.start == datetime(2026, 10, 1, 5, 0, tzinfo=UTC)
    assert period.end == datetime(2026, 11, 1, 5, 0, tzinfo=UTC)


def test_the_month_rolls_over_the_year() -> None:
    period = month_period(datetime(2026, 12, 15, 12, 0, tzinfo=UTC), "America/Bogota")

    assert period.start == datetime(2026, 12, 1, 5, 0, tzinfo=UTC)
    assert period.end == datetime(2027, 1, 1, 5, 0, tzinfo=UTC)


# ── persistencia de la política ───────────────────────────────────────────────────────────
async def test_ai_limits_survive_a_reload(services: CloudLinkServices) -> None:
    limits = AiLimits(
        allowed_providers=frozenset({"claude", "gemini"}),
        user_monthly_usd=Decimal("5.5"),
        provider_monthly_usd={"gemini": Decimal("50")},
        user_overrides={"a" * 32: Decimal("20")},
    )
    await _link(services, limits)

    stored = (await services.repository.get()).effective_policy.ai

    assert stored == limits


async def test_a_policy_stored_before_m3_has_no_ai_limits(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> None:
    from sqlalchemy import update

    from app.modules.cloud_link.infrastructure.persistence.models import CloudLinkModel

    await services.repository.get()
    async with sm() as session:
        await session.execute(update(CloudLinkModel).values(policy={"sync_enabled": True}))
        await session.commit()

    assert (await services.repository.get()).effective_policy.ai is None
