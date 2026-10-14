from uuid import UUID

from app.modules.feedback.domain.interfaces import FeedbackReportRepository
from app.modules.feedback.domain.value_objects import (
    FeedbackFilters,
    FeedbackPage,
    FeedbackReportItem,
    FeedbackSummary,
)

# Tope del export: suficiente para un piloto, evita volcar la tabla entera.
EXPORT_MAX_ROWS = 10_000


class ListFeedbackUseCase:
    def __init__(self, repository: FeedbackReportRepository) -> None:
        self._repository = repository

    async def execute(
        self, *, owner_erp_database_id: UUID, filters: FeedbackFilters, limit: int, offset: int
    ) -> FeedbackPage:
        return await self._repository.list_feedback(
            owner_erp_database_id=owner_erp_database_id,
            filters=filters,
            limit=limit,
            offset=offset,
        )


class GetFeedbackSummaryUseCase:
    def __init__(self, repository: FeedbackReportRepository) -> None:
        self._repository = repository

    async def execute(
        self, *, owner_erp_database_id: UUID, filters: FeedbackFilters
    ) -> FeedbackSummary:
        return await self._repository.summary(
            owner_erp_database_id=owner_erp_database_id, filters=filters
        )


class ExportFeedbackUseCase:
    def __init__(self, repository: FeedbackReportRepository) -> None:
        self._repository = repository

    async def execute(
        self, *, owner_erp_database_id: UUID, filters: FeedbackFilters
    ) -> list[FeedbackReportItem]:
        return await self._repository.export_rows(
            owner_erp_database_id=owner_erp_database_id,
            filters=filters,
            max_rows=EXPORT_MAX_ROWS,
        )
