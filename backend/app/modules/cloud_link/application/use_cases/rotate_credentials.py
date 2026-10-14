import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from app.modules.cloud_link.application.link_failures import record_cloud_failure
from app.modules.cloud_link.domain.entities import CloudLinkState, CloudNotice
from app.modules.cloud_link.domain.exceptions import CloudApiError
from app.modules.cloud_link.domain.interfaces import CloudApi, CloudLinkRepository

logger = logging.getLogger(__name__)

# La instancia rota sola cada 90 días y cuando la consola lo pide (§3.4).
ROTATE_EVERY = timedelta(days=90)
ROTATE_NOTICE_CODE = "rotate_credentials"


# Si Cloud tardara en retirar el aviso, no se rota en cada heartbeat.
_NOTICE_COOLDOWN = timedelta(minutes=10)


def rotation_due(state: CloudLinkState, notices: list[CloudNotice], now: datetime) -> bool:
    since = state.secret_rotated_at or state.linked_at
    if any(n.code == ROTATE_NOTICE_CODE for n in notices):
        return since is None or now - since >= _NOTICE_COOLDOWN
    return since is not None and now - since >= ROTATE_EVERY


class RotateCredentialsUseCase:
    def __init__(
        self,
        repository: CloudLinkRepository,
        cloud_api: CloudApi,
        *,
        now: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._cloud_api = cloud_api
        self._now = now

    async def execute(self) -> bool:
        """`True` si el secreto se rotó. Un fallo no tumba nada: se reintenta
        en el próximo heartbeat."""
        state = await self._repository.get()
        if not state.has_credentials or state.secret is None or not state.status.syncs:
            return False
        now = self._now()
        try:
            new_secret = await self._cloud_api.rotate(
                cloud_url=state.cloud_url, secret=state.secret
            )
        except CloudApiError as error:
            logger.warning("No se pudo rotar el secreto de SAVI Cloud (%s).", error.error_code)
            await record_cloud_failure(self._repository, error, now, from_heartbeat=False)
            return False

        # Se guarda el nuevo antes que nada: Cloud mantiene el anterior válido
        # 24 horas, pero perder el nuevo dejaría a la instancia afuera.
        def mutate(s: CloudLinkState) -> None:
            s.secret = new_secret
            s.secret_rotated_at = now

        await self._repository.update(mutate)
        return True
