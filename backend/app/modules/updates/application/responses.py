from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.modules.updates.application.coordinator import ApplyPhase, UpdateSnapshot
from app.modules.updates.domain.value_objects import InstallOutcome, InstallRecord, UpdateState


class InstallRecordResponse(BaseModel):
    """Un intento de instalación ya resuelto."""

    attempt_id: str
    from_version: str
    to_version: str
    outcome: InstallOutcome
    started_at: datetime
    finished_at: datetime
    exit_code: int | None = None
    # Texto para la persona, de usted.
    message: str

    @classmethod
    def from_record(cls, record: InstallRecord) -> InstallRecordResponse:
        return cls(
            attempt_id=record.attempt_id,
            from_version=str(record.from_version),
            to_version=str(record.to_version),
            outcome=record.outcome,
            started_at=record.started_at,
            finished_at=record.finished_at,
            exit_code=record.exit_code,
            message=record.message,
        )


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
    # El último intento de instalación: la interfaz lo avisa una sola vez.
    last_install: InstallRecordResponse | None = None

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
            last_install=(
                InstallRecordResponse.from_record(snapshot.last_install)
                if snapshot.last_install
                else None
            ),
        )
