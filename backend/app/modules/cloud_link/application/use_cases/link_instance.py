from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlsplit

from app.modules.cloud_link.domain.entities import EPOCH, CloudLinkState
from app.modules.cloud_link.domain.exceptions import (
    AlreadyLinkedError,
    CloudApiError,
    CloudNotConfiguredError,
    InsecureCloudUrlError,
)
from app.modules.cloud_link.domain.interfaces import (
    CloudApi,
    CloudLinkRepository,
    InstanceInfoProvider,
    JsonObject,
)
from app.modules.cloud_link.domain.value_objects import (
    INCREMENTAL_STREAMS,
    HistoryMode,
    LinkStatus,
)


def normalize_cloud_url(raw: str, *, allow_insecure_http: bool) -> str:
    """URL base de Cloud sin barra final. `https` siempre; `http` solo en
    desarrollo."""
    url = raw.strip().rstrip("/")
    if not url:
        raise CloudNotConfiguredError
    parts = urlsplit(url)
    if not parts.hostname or parts.scheme not in ("https", "http"):
        raise InsecureCloudUrlError
    if parts.scheme == "http" and not allow_insecure_http:
        raise InsecureCloudUrlError
    return url


class LinkInstanceUseCase:
    def __init__(
        self,
        repository: CloudLinkRepository,
        cloud_api: CloudApi,
        info_provider: InstanceInfoProvider,
        *,
        allow_insecure_http: bool,
        now: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._cloud_api = cloud_api
        self._info_provider = info_provider
        self._allow_insecure_http = allow_insecure_http
        self._now = now

    async def execute(
        self, *, cloud_url: str, token: str, history: HistoryMode = HistoryMode.ALL
    ) -> CloudLinkState:
        url = normalize_cloud_url(cloud_url, allow_insecure_http=self._allow_insecure_http)
        state = await self._repository.get()
        if state.status != LinkStatus.UNLINKED:
            raise AlreadyLinkedError

        info = self._info_provider.describe(state.install_id)
        instance: JsonObject = {
            "name": info.name,
            "deployment_mode": info.deployment_mode,
            "version": info.version,
            "commit": info.commit,
            "os": info.os,
            "agent_db_engine": info.agent_db_engine,
            "fingerprint": info.fingerprint,
        }

        # Las marcas se fijan ANTES de canjear: si el canje falla no hay nada
        # que sincronizar, y si sale bien la vinculación queda completa en un
        # solo paso, sin una ventana en la que existan credenciales y no la
        # decisión de historial.
        now = self._now()
        start = EPOCH if history == HistoryMode.ALL else now
        await self._repository.reset_watermarks([s.value for s in INCREMENTAL_STREAMS], start)

        try:
            result = await self._cloud_api.enroll(
                cloud_url=url, token=token.strip(), instance=instance
            )
        except CloudApiError as error:
            code = error.error_code
            await self._repository.update(lambda s: _record_enroll_failure(s, code, now))
            raise

        def mutate(s: CloudLinkState) -> None:
            s.cloud_url = url
            s.status = LinkStatus.LINKED
            s.instance_id = result.instance_id
            s.client_code = result.client_code
            s.client_name = result.client_name
            s.secret = result.instance_secret
            s.policy = result.policy
            s.notices = []
            s.linked_at = now
            s.last_attempt_at = now
            s.last_heartbeat_ok_at = now
            s.secret_rotated_at = now
            s.last_error_code = None
            s.consecutive_failures = 0

        return await self._repository.update(mutate)


def _record_enroll_failure(state: CloudLinkState, error_code: str, now: datetime) -> None:
    state.last_attempt_at = now
    state.last_error_code = error_code[:64]
