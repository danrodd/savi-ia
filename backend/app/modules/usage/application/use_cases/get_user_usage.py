from app.modules.usage.application.dtos import UserUsageReportDTO
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.domain.value_objects import UsagePeriod


class GetUserUsageUseCase:
    """Consumo de UN usuario en un período: total + desglose diario."""

    def __init__(self, repository: UsageRepository):
        self._repository = repository

    async def execute(
        self, user_id: int, period: UsagePeriod
    ) -> UserUsageReportDTO:
        totals = await self._repository.totals_for_user(user_id, period)
        daily = await self._repository.daily_for_user(user_id, period)
        return UserUsageReportDTO(
            user_id=user_id,
            period_start=period.start,
            period_end=period.end,
            totals=totals,
            daily=daily,
        )
