from dataclasses import dataclass
from datetime import UTC, datetime

# Marca inicial de "enviar el historial completo".
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class StreamWatermark:
    stream: str
    at: datetime
    # Para streams incrementales, el id de la última fila vista. Para
    # `database`, el hash del último inventario enviado.
    id: str
    last_ok_at: datetime | None = None
