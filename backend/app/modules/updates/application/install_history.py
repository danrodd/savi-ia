"""Da por resuelto el intento de instalación que dejó el vigilante.

Se corre al arrancar: es el SAVI nuevo (o el viejo, si la instalación no se
aplicó) quien sabe en qué versión quedó, y por eso es quien decide cómo terminó
el intento.
"""

from __future__ import annotations

from datetime import datetime

from app.modules.updates.domain.interfaces import InstallHistory, InstallResultReader
from app.modules.updates.domain.value_objects import (
    HISTORY_LIMIT,
    InstallRecord,
    ReleaseVersion,
    settle,
)


def reconcile_last_install(
    *,
    results: InstallResultReader,
    history: InstallHistory,
    running: ReleaseVersion,
    now: datetime,
) -> InstallRecord | None:
    """El registro nuevo que se agregó al historial, o `None` si no había nada pendiente."""
    result = results.read()
    if result is None:
        return None
    if any(record.attempt_id == result.attempt_id for record in history.recent(HISTORY_LIMIT)):
        return None
    record = settle(result, running, now)
    history.append(record)
    return record
