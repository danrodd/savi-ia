from dataclasses import dataclass
from enum import StrEnum

# Tope duro del contrato `sync/v1` (eventos por lote) y piso del reintento
# cuando Cloud responde 413.
CONTRACT_MAX_BATCH_EVENTS = 500
MIN_BATCH_EVENTS = 50


class SyncStream(StrEnum):
    TURN = "turn"
    CONVERSATION = "conversation"
    SESSION = "session"
    FREE_QUERY = "free_query"
    DATABASE = "database"

    @property
    def schema(self) -> str:
        """Valor del campo `schema` de cada evento del stream."""
        return f"{self.value}/1"


INCREMENTAL_STREAMS: tuple[SyncStream, ...] = (
    SyncStream.TURN,
    SyncStream.CONVERSATION,
    SyncStream.SESSION,
    SyncStream.FREE_QUERY,
)


@dataclass(frozen=True, slots=True)
class SyncPolicy:
    """Política que Cloud informa en el enroll y en cada heartbeat."""

    heartbeat_seconds: int = 300
    ingest_seconds: int = 300
    max_batch_events: int = CONTRACT_MAX_BATCH_EVENTS
    sync_enabled: bool = True
