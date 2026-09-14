from uuid import UUID

from app.modules.usage.application.dtos import UserUsageReportDTO
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.domain.value_objects import UsageFilters, UsagePeriod


class GetUserUsageUseCase:
    """Consumo de UN usuario en un período: total + desglose diario."""

    def __init__(self, repository: UsageRepository):
        self._repository = repository

    async def execute(
        self,
        user_id: int,
        period: UsagePeriod,
        *,
        erp_database_id: UUID,
        filters: UsageFilters | None = None,
    ) -> UserUsageReportDTO:
        # `erp_database_id` no es opcional: sin él, el consumo del usuario
        # 5 sumaría el de todos los usuarios 5 de los demás clientes.
        totals = await self._repository.totals_for_user(
            user_id, period, erp_database_id=erp_database_id, filters=filters
        )
        daily = await self._repository.daily_for_user(
            user_id, period, erp_database_id=erp_database_id, filters=filters
        )
        return UserUsageReportDTO(
            user_id=user_id,
            period_start=period.start,
            period_end=period.end,
            totals=totals,
            daily=daily,
        )
