"""Respuestas del API de administración. Ninguna lleva el secreto de la
instancia ni la clave de seudónimos: no existen como campos."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.modules.cloud_link.domain.entities import CloudLinkState, StreamWatermark


class NoticeResponse(BaseModel):
    code: str
    severity: str
    message: str


class StreamStatusResponse(BaseModel):
    stream: str
    watermark_at: datetime
    last_ok_at: datetime | None


class CloudLinkStatusResponse(BaseModel):
    status: str
    # Falso si la instalación no tiene `SAVI_CLOUD_URL`: no se puede vincular.
    cloud_configured: bool
    sync_enabled: bool
    client_code: str | None
    client_name: str | None
    instance_id: UUID | None
    linked_at: datetime | None
    last_heartbeat_ok_at: datetime | None
    last_attempt_at: datetime | None
    last_error_code: str | None
    streams: list[StreamStatusResponse]
    notices: list[NoticeResponse]

    @classmethod
    def build(
        cls,
        state: CloudLinkState,
        watermarks: list[StreamWatermark],
        *,
        cloud_configured: bool,
        sync_enabled: bool,
    ) -> CloudLinkStatusResponse:
        return cls(
            status=state.status.value,
            cloud_configured=cloud_configured,
            sync_enabled=sync_enabled,
            client_code=state.client_code,
            client_name=state.client_name,
            instance_id=state.instance_id,
            linked_at=state.linked_at,
            last_heartbeat_ok_at=state.last_heartbeat_ok_at,
            last_attempt_at=state.last_attempt_at,
            last_error_code=state.last_error_code,
            streams=[
                StreamStatusResponse(stream=w.stream, watermark_at=w.at, last_ok_at=w.last_ok_at)
                for w in sorted(watermarks, key=lambda w: w.stream)
            ],
            notices=[
                NoticeResponse(code=n.code, severity=n.severity, message=n.message)
                for n in state.notices
            ],
        )


class SyncNowResponse(BaseModel):
    accepted: bool = True


class PreviewResponse(BaseModel):
    heartbeat: dict[str, Any]
    events: dict[str, dict[str, Any] | None]
