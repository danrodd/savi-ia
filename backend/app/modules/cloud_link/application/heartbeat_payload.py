"""Arma el cuerpo del heartbeat. Lo usan el heartbeat real y la pantalla de
transparencia, así lo que se muestra es lo que viaja."""

from collections.abc import Callable
from datetime import datetime

from app.modules.cloud_link.domain.entities import CloudLinkState, iso_utc
from app.modules.cloud_link.domain.interfaces import (
    CloudLinkRepository,
    InstanceInfoProvider,
    JsonObject,
    LocalTelemetry,
)


class HeartbeatPayloadBuilder:
    def __init__(
        self,
        repository: CloudLinkRepository,
        info_provider: InstanceInfoProvider,
        telemetry: LocalTelemetry,
        now: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._info_provider = info_provider
        self._telemetry = telemetry
        self._now = now

    async def build(self, state: CloudLinkState) -> JsonObject:
        info = self._info_provider.describe(state.install_id)
        snapshot = await self._telemetry.collect()
        watermarks = await self._repository.list_watermarks()
        streams: dict[str, JsonObject] = {
            w.stream: {
                "watermark_at": iso_utc(w.at),
                "last_ok_at": iso_utc(w.last_ok_at) if w.last_ok_at is not None else None,
            }
            for w in watermarks
        }
        return {
            "sent_at": iso_utc(self._now()),
            "fingerprint": info.fingerprint,
            "version": info.version,
            "commit": info.commit,
            "deployment_mode": info.deployment_mode,
            "started_at": iso_utc(info.started_at) if info.started_at is not None else None,
            "tls": snapshot.tls,
            "llm": {
                "provider": snapshot.llm.provider,
                "model": snapshot.llm.model,
                "credential_kind": snapshot.llm.credential_kind,
                "usable": snapshot.llm.usable,
            },
            "erp_databases": {
                "total": snapshot.databases_total,
                "usable": snapshot.databases_usable,
                "credentials_unreadable": snapshot.databases_unreadable,
            },
            "active_sessions": snapshot.active_sessions,
            "sync": {"streams": streams, "last_error": state.last_error_code},
            "warnings": list(snapshot.warnings),
        }
