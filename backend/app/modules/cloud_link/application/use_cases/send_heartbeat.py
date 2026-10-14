from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.modules.cloud_link.application.heartbeat_payload import HeartbeatPayloadBuilder
from app.modules.cloud_link.application.link_failures import (
    CONTRACT_REJECTED,
    record_cloud_failure,
)
from app.modules.cloud_link.application.use_cases.rotate_credentials import (
    RotateCredentialsUseCase,
    rotation_due,
)
from app.modules.cloud_link.domain.entities import CloudLinkState
from app.modules.cloud_link.domain.exceptions import CloudApiError
from app.modules.cloud_link.domain.interfaces import CloudApi, CloudLinkRepository
from app.modules.cloud_link.domain.value_objects import LinkStatus


@dataclass(frozen=True, slots=True)
class HeartbeatOutcome:
    sent: bool
    ok: bool = False
    # Pista de Cloud (`Retry-After`) para el backoff del scheduler.
    retry_after_seconds: float | None = None


class SendHeartbeatUseCase:
    def __init__(
        self,
        repository: CloudLinkRepository,
        cloud_api: CloudApi,
        payload_builder: HeartbeatPayloadBuilder,
        rotate: RotateCredentialsUseCase,
        *,
        now: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._cloud_api = cloud_api
        self._payload_builder = payload_builder
        self._rotate = rotate
        self._now = now

    async def execute(self) -> HeartbeatOutcome:
        state = await self._repository.get()
        if not state.status.sends_heartbeat or not state.has_credentials or state.secret is None:
            return HeartbeatOutcome(sent=False)

        now = self._now()
        payload = await self._payload_builder.build(state)
        try:
            result = await self._cloud_api.heartbeat(
                cloud_url=state.cloud_url, secret=state.secret, payload=payload
            )
        except CloudApiError as error:
            await record_cloud_failure(self._repository, error, now, from_heartbeat=True)
            return HeartbeatOutcome(
                sent=True, ok=False, retry_after_seconds=error.retry_after_seconds
            )

        def mutate(s: CloudLinkState) -> None:
            s.last_attempt_at = now
            s.last_heartbeat_ok_at = now
            s.consecutive_failures = 0
            s.policy = result.policy
            s.notices = result.notices
            if s.last_error_code != CONTRACT_REJECTED:
                s.last_error_code = None
            if result.instance_status == "active":
                s.status = LinkStatus.LINKED
            elif result.instance_status == "suspended":
                s.status = LinkStatus.SUSPENDED
            elif result.instance_status == "revoked":
                s.status = LinkStatus.REVOKED
                s.secret = None

        updated = await self._repository.update(mutate)
        if updated.status == LinkStatus.LINKED and rotation_due(updated, updated.notices, now):
            await self._rotate.execute()
        return HeartbeatOutcome(sent=True, ok=True)
