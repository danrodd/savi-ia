"""Aplica la política de IA de Cloud antes de cada turno (M3).

Orden de las comprobaciones, de la más barata a la más cara:

1. Proveedor permitido.
2. Hay precio para medir (Gemini y OpenAI no informan costo: sin precio cargado un tope en USD
   no se activaría nunca, y eso es peor que bloquear con un mensaje claro).
3. Tope mensual por persona (excepción propia o general).
4. Tope mensual del proveedor para toda la instalación.

Sin vinculación a Cloud, o sin política de IA, no hay límites.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.chat.domain.exceptions import AiAccessDeniedError
from app.modules.chat.domain.interfaces import ActiveProvider, AiBudgetGuard
from app.modules.cloud_link.application.pseudonymizer import PseudonymizerProvider
from app.modules.cloud_link.domain.interfaces import CloudLinkRepository
from app.modules.cloud_link.domain.value_objects import AiLimits
from app.modules.llm_providers.domain.entities import get_descriptor
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.domain.value_objects import UsagePeriod
from app.modules.usage.infrastructure.persistence.repositories.sqlalchemy_usage_repository import (
    SqlAlchemyUsageRepository,
)

PROVIDER_NOT_ALLOWED = "ai_provider_not_allowed"
BUDGET_EXCEEDED = "ai_budget_exceeded"
PRICE_MISSING = "ai_price_missing"

_DISPLAY = {"claude": "Claude", "gemini": "Gemini", "openai": "OpenAI"}


def month_period(now: datetime, timezone: str) -> UsagePeriod:
    """Mes calendario en la zona de reporte: el "1 del mes" de Bogotá, no el de UTC."""
    tz = ZoneInfo(timezone)
    local = now.astimezone(tz)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return UsagePeriod(start=start.astimezone(UTC), end=end.astimezone(UTC))


def _usd(amount: Decimal) -> str:
    return f"USD {amount.quantize(Decimal('0.01'))}"


UsageSource = Callable[[], AbstractAsyncContextManager[UsageRepository]]


def sql_usage_source(
    sessionmaker: async_sessionmaker[AsyncSession], reporting_timezone: str
) -> UsageSource:
    """Un repositorio de consumo sobre una sesión corta propia (no la del request)."""

    @asynccontextmanager
    async def source() -> AsyncGenerator[UsageRepository]:
        async with sessionmaker() as session:
            yield SqlAlchemyUsageRepository(session, reporting_timezone=reporting_timezone)

    return source


class CloudAiBudgetGuard(AiBudgetGuard):
    def __init__(
        self,
        repository: CloudLinkRepository,
        pseudonymizers: PseudonymizerProvider,
        usage: UsageSource,
        reporting_timezone: str,
    ) -> None:
        self._repository = repository
        self._pseudonymizers = pseudonymizers
        self._usage = usage
        self._timezone = reporting_timezone

    async def check(
        self, *, user_id: int, erp_database_id: UUID, provider: ActiveProvider
    ) -> None:
        state = await self._repository.get()
        limits = state.effective_policy.ai if state.has_credentials else None
        if limits is None or limits.is_unlimited:
            return

        self._check_provider(limits, provider)

        user_ref = (await self._pseudonymizers.get()).user_ref(erp_database_id, user_id)
        user_cap = limits.user_cap(user_ref)
        provider_cap = limits.provider_monthly_usd.get(provider.kind)
        if user_cap is None and provider_cap is None:
            return

        self._check_priced(provider)
        if user_cap is not None and user_cap == 0:
            raise AiAccessDeniedError(
                BUDGET_EXCEEDED, "SEO Group no habilitó el uso de IA para tu usuario."
            )

        period = month_period(datetime.now(UTC), self._timezone)
        async with self._usage() as usage:
            if user_cap is not None:
                rows = await usage.provider_totals_for_user(
                    user_id, period, erp_database_id=erp_database_id
                )
                spent = sum((r.totals.cost_usd for r in rows), Decimal("0"))
                if spent >= user_cap:
                    raise AiAccessDeniedError(
                        BUDGET_EXCEEDED,
                        f"Llegaste al tope mensual de IA ({_usd(user_cap)}). "
                        "Se renueva el primer día del mes; si lo necesitás antes, "
                        "pedíselo a SEO Group.",
                    )
            if provider_cap is not None:
                system = await usage.provider_totals_system(period)
                pool = sum(
                    (r.totals.cost_usd for r in system if r.provider == provider.kind),
                    Decimal("0"),
                )
                if pool >= provider_cap:
                    name = _DISPLAY.get(provider.kind, provider.kind)
                    raise AiAccessDeniedError(
                        BUDGET_EXCEEDED,
                        f"La instalación llegó al tope mensual de {name} "
                        f"({_usd(provider_cap)}). Se renueva el primer día del mes.",
                    )

    @staticmethod
    def _check_provider(limits: AiLimits, provider: ActiveProvider) -> None:
        allowed = limits.allowed_providers
        if allowed is not None and provider.kind not in allowed:
            name = _DISPLAY.get(provider.kind, provider.kind)
            raise AiAccessDeniedError(
                PROVIDER_NOT_ALLOWED,
                f"SEO Group no habilitó {name} para esta instalación. "
                "Un administrador tiene que activar otro proveedor de IA.",
            )

    @staticmethod
    def _check_priced(provider: ActiveProvider) -> None:
        """Con tope en USD hay que poder calcular el costo del modelo en uso."""
        if get_descriptor(provider.kind).reports_cost:
            return
        if provider.chat_model in provider.pricing:
            return
        raise AiAccessDeniedError(
            PRICE_MISSING,
            f"Hay un tope de gasto de IA y el modelo {provider.chat_model} no tiene "
            "precio cargado, así que no se puede medir. Un administrador tiene que "
            "cargar el precio en Proveedores de IA.",
        )
