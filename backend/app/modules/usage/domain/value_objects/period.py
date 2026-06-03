from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class UsagePeriod:
    """Rango temporal [start, end) sobre el que se agrega el consumo.

    Half-open por convención: incluye `start`, excluye `end`. Ambos son
    timezone-aware (UTC) — el bucketing por día local lo resuelve el
    repositorio con la zona de reporte.
    """

    start: datetime
    end: datetime
