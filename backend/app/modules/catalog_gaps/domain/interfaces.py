from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.modules.catalog_gaps.domain.value_objects import GapEvent


class GapEventReader(ABC):
    @abstractmethod
    async def events(
        self,
        owner_erp_database_id: UUID,
        start: datetime,
        end: datetime,
        query_limit: int,
    ) -> list[GapEvent]:
        """Las señales del periodo `[start, end)` en las conversaciones de esa base.

        `query_limit`: consultas al ERP por turno; el turno que las gastó todas y
        recibió el rechazo cuenta como `query_limit`.
        """
