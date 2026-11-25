from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.modules.catalog_gaps.application.build_report import build_report
from app.modules.catalog_gaps.domain.interfaces import GapEventReader
from app.modules.catalog_gaps.domain.value_objects import CatalogGapReport


class GetCatalogGapsUseCase:
    def __init__(self, reader: GapEventReader, query_limit: int) -> None:
        self._reader = reader
        self._query_limit = query_limit

    async def execute(
        self, owner_erp_database_id: UUID, start: datetime, end: datetime
    ) -> CatalogGapReport:
        events = await self._reader.events(owner_erp_database_id, start, end, self._query_limit)
        return build_report(events, start, end)
