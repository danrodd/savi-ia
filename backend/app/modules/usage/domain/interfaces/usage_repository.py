from abc import ABC, abstractmethod

from app.modules.usage.domain.value_objects import (
    ConversationStats,
    ConversationUsage,
    DailyUsage,
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
        self, user_id: int, period: UsagePeriod
    ) -> UsageTotals: ...

    @abstractmethod
    async def daily_for_user(
        self, user_id: int, period: UsagePeriod
    ) -> list[DailyUsage]: ...

    @abstractmethod
    async def system_totals(self, period: UsagePeriod) -> UsageTotals: ...

    @abstractmethod
    async def per_user(self, period: UsagePeriod) -> list[UserUsage]: ...

    @abstractmethod
    async def daily_system(self, period: UsagePeriod) -> list[DailyUsage]: ...

    @abstractmethod
    async def conversation_stats(self, period: UsagePeriod) -> ConversationStats: ...

    @abstractmethod
    async def user_stats(self, period: UsagePeriod) -> UserStats: ...

    @abstractmethod
    async def per_conversation(
        self, period: UsagePeriod, *, limit: int
    ) -> list[ConversationUsage]: ...
