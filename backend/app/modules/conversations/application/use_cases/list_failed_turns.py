from uuid import UUID

from app.modules.conversations.domain.interfaces.failed_turn_reader import (
    FailedTurn,
    FailedTurnReader,
)

FAILED_TURNS_LIMIT_MAX = 200


class ListFailedTurnsUseCase:
    def __init__(self, reader: FailedTurnReader) -> None:
        self._reader = reader

    async def execute(self, owner_erp_database_id: UUID, limit: int = 50) -> list[FailedTurn]:
        bounded = max(1, min(limit, FAILED_TURNS_LIMIT_MAX))
        return await self._reader.recent(owner_erp_database_id, bounded)
