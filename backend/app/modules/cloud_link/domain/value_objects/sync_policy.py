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


# Valores de `identity_mode` que esta instalación entiende. Uno desconocido se trata como
# `pseudonym`: ante la duda, lo más privado.
IDENTITY_PSEUDONYM = "pseudonym"
IDENTITY_NAMED = "named"


@dataclass(frozen=True, slots=True)
class SyncPolicy:
    """Política que Cloud informa en el enroll y en cada heartbeat."""

    heartbeat_seconds: int = 300
    ingest_seconds: int = 300
    max_batch_events: int = CONTRACT_MAX_BATCH_EVENTS
    sync_enabled: bool = True
    # Esta instalación queda solo con el chat: SEO Group la administra desde Cloud.
    config_locked: bool = False
    # `named`: las sesiones llevan el código de usuario (organización interna). Por defecto,
    # solo seudónimos.
    identity_mode: str = "pseudonym"
