"""Transiciones de estado ante un error de Cloud (§5.6). Compartidas por el
heartbeat, el ciclo de envío y la rotación."""

from datetime import datetime, timedelta

from app.modules.cloud_link.domain.entities import CloudLinkState
from app.modules.cloud_link.domain.exceptions import CloudApiError
from app.modules.cloud_link.domain.interfaces import CloudLinkRepository
from app.modules.cloud_link.domain.value_objects import LinkStatus

# Sin respuesta de heartbeat durante este tiempo, la instancia pasa a `offline`.
OFFLINE_AFTER = timedelta(minutes=15)

CONTRACT_REJECTED = "contract_rejected"
_ERROR_CODE_MAX = 64


def _silent_since(state: CloudLinkState) -> datetime | None:
    return state.last_heartbeat_ok_at or state.linked_at


async def record_cloud_failure(
    repository: CloudLinkRepository,
    error: CloudApiError,
    now: datetime,
    *,
    from_heartbeat: bool,
) -> CloudLinkState:
    """Guarda el fallo y aplica la transición que corresponde."""

    def mutate(state: CloudLinkState) -> None:
        state.last_attempt_at = now
        state.last_error_code = error.error_code[:_ERROR_CODE_MAX]
        if error.is_revoked:
            state.status = LinkStatus.REVOKED
            state.secret = None
            state.consecutive_failures = 0
        elif error.is_unauthorized:
            state.status = LinkStatus.UNAUTHORIZED
            state.consecutive_failures = 0
        elif error.is_transient:
            state.consecutive_failures += 1
            since = _silent_since(state)
            if (
                from_heartbeat
                and state.status == LinkStatus.LINKED
                and since is not None
                and now - since >= OFFLINE_AFTER
            ):
                state.status = LinkStatus.OFFLINE

    return await repository.update(mutate)
