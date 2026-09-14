from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.domain.value_objects import (
    ConversationUsage,
    UsageFilters,
    UsagePeriod,
)


class ListConversationUsageUseCase:
    """Lista el consumo por conversación (las más caras primero).

    Alimenta la tabla de "conversaciones más pesadas", el histograma de
    distribución y el export CSV de la vista de KPIs.
    """

    def __init__(self, repository: UsageRepository):
        self._repository = repository

    async def execute(
        self,
        period: UsagePeriod,
        *,
        limit: int,
        filters: UsageFilters | None = None,
    ) -> list[ConversationUsage]:
        return await self._repository.per_conversation(period, limit=limit, filters=filters)
