from app.modules.usage.application.dtos import SystemUsageReportDTO
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.domain.value_objects import UsagePeriod


class GetSystemUsageUseCase:
    """Consumo global del sistema: total + ranking por usuario + serie diaria.

    Pensado para la vista administrativa. La autorización (solo admins)
    se aplica en la capa HTTP, no acá.
    """

    def __init__(self, repository: UsageRepository):
        self._repository = repository

    async def execute(self, period: UsagePeriod) -> SystemUsageReportDTO:
        totals = await self._repository.system_totals(period)
        per_user = await self._repository.per_user(period)
        daily = await self._repository.daily_system(period)
        return SystemUsageReportDTO(
            period_start=period.start,
            period_end=period.end,
            totals=totals,
            per_user=per_user,
            daily=daily,
        )
