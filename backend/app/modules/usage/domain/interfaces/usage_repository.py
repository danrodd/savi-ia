from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.usage.domain.value_objects import (
    ConversationStats,
    ConversationUsage,
    DailyProviderUsage,
    DailyUsage,
    DatabaseUsage,
    ProviderUsage,
    UsageFilters,
    UsagePeriod,
    UsageTotals,
    UserStats,
    UserUsage,
)


class UsageRepository(ABC):
    """Puerto de lectura del consumo agregado.

    Todas las consultas cuentan los turnos del asistente que incurrieron
    en costo — INCLUIDOS los de conversaciones borradas y los mensajes
    `superseded` (editados/regenerados). Esos tokens se pagaron de verdad;
    para medir consumo real y fijar precios esa es la cifra honesta.
    """

    @abstractmethod
    async def totals_for_user(
        self,
        user_id: int,
        period: UsagePeriod,
        *,
        erp_database_id: UUID,
        filters: UsageFilters | None = None,
    ) -> UsageTotals: ...

    @abstractmethod
    async def daily_for_user(
        self,
        user_id: int,
        period: UsagePeriod,
        *,
        erp_database_id: UUID,
        filters: UsageFilters | None = None,
    ) -> list[DailyUsage]: ...

    @abstractmethod
    async def provider_totals_for_user(
        self,
        user_id: int,
        period: UsagePeriod,
        *,
        erp_database_id: UUID,
        filters: UsageFilters | None = None,
    ) -> list[ProviderUsage]: ...

    @abstractmethod
    async def daily_provider_for_user(
        self,
        user_id: int,
        period: UsagePeriod,
        *,
        erp_database_id: UUID,
        filters: UsageFilters | None = None,
    ) -> list[DailyProviderUsage]: ...

    @abstractmethod
    async def system_totals(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> UsageTotals: ...

    @abstractmethod
    async def per_user(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> list[UserUsage]: ...

    @abstractmethod
    async def daily_system(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> list[DailyUsage]: ...

    @abstractmethod
    async def provider_totals_system(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> list[ProviderUsage]: ...

    @abstractmethod
    async def database_totals_system(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> list[DatabaseUsage]: ...

    @abstractmethod
    async def daily_provider_system(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> list[DailyProviderUsage]: ...

    @abstractmethod
    async def conversation_stats(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> ConversationStats: ...

    @abstractmethod
    async def user_stats(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> UserStats: ...

    @abstractmethod
    async def per_conversation(
        self,
        period: UsagePeriod,
        *,
        limit: int,
        filters: UsageFilters | None = None,
    ) -> list[ConversationUsage]: ...
