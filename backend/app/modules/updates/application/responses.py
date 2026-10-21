from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.modules.updates.application.coordinator import ApplyPhase, UpdateSnapshot
from app.modules.updates.domain.value_objects import UpdateState


class UpdateStatusResponse(BaseModel):
    # `False` en desarrollo o sin servidor configurado: la interfaz no muestra nada.
    enabled: bool
    state: UpdateState
    current_version: str | None
    available_version: str | None = None
    notes: str | None = None
    published_at: datetime | None = None
    size: int | None = None
    # Solo con `state = required`: hasta cuándo se puede seguir sin actualizar.
    deadline: datetime | None = None
    # Desde otro equipo no se puede aceptar el UAC del servidor.
    can_apply: bool = False
    phase: ApplyPhase = ApplyPhase.IDLE
    downloaded_bytes: int = 0
    error: str | None = None
    checked_at: datetime | None = None

    @classmethod
    def disabled(cls) -> UpdateStatusResponse:
        return cls(enabled=False, state=UpdateState.UP_TO_DATE, current_version=None)

    @classmethod
    def from_snapshot(cls, snapshot: UpdateSnapshot, *, can_apply: bool) -> UpdateStatusResponse:
        decision = snapshot.decision
        manifest = decision.manifest
        return cls(
            enabled=True,
            state=decision.state,
            current_version=str(decision.current),
            available_version=str(manifest.version) if manifest else None,
            notes=manifest.notes if manifest else None,
            published_at=manifest.published_at if manifest else None,
            size=manifest.size if manifest else None,
            deadline=decision.deadline,
            can_apply=can_apply,
            phase=snapshot.phase,
            downloaded_bytes=snapshot.downloaded_bytes,
            error=snapshot.apply_error,
            checked_at=snapshot.checked_at,
        )
