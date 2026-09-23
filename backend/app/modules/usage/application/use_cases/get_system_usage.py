from app.modules.usage.application.dtos import SystemUsageReportDTO
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.domain.value_objects import UsageFilters, UsagePeriod


class GetSystemUsageUseCase:
    """Consumo global del sistema: total + ranking por usuario + serie diaria.

    Pensado para la vista administrativa. La autorización (solo admins)
    se aplica en la capa HTTP, no acá.
    """

    def __init__(self, repository: UsageRepository):
        self._repository = repository

    async def execute(
        self, period: UsagePeriod, *, filters: UsageFilters | None = None
    ) -> SystemUsageReportDTO:
        totals = await self._repository.system_totals(period, filters=filters)
        per_user = await self._repository.per_user(period, filters=filters)
        daily = await self._repository.daily_system(period, filters=filters)
        per_provider = await self._repository.provider_totals_system(period, filters=filters)
        daily_by_provider = await self._repository.daily_provider_system(period, filters=filters)
        per_database = await self._repository.database_totals_system(period, filters=filters)
        return SystemUsageReportDTO(
            period_start=period.start,
            period_end=period.end,
            totals=totals,
            per_user=per_user,
            daily=daily,
            per_provider=per_provider,
            daily_by_provider=daily_by_provider,
            per_database=per_database,
        )
