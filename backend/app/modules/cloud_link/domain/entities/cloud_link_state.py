"""Estado de la vinculación (singleton). El secreto y la clave de seudónimos
viajan en claro dentro del dominio; el repositorio es la frontera del cifrado
y ningún DTO de salida los tiene."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.modules.cloud_link.domain.value_objects import LinkStatus, SyncPolicy


@dataclass(frozen=True, slots=True)
class CloudNotice:
    code: str
    severity: str
    message: str


@dataclass(slots=True)
class CloudLinkState:
    cloud_url: str
    install_id: UUID
    # 32 bytes aleatorios. Nunca salen de la instancia.
    pseudonym_key: bytes
    status: LinkStatus = LinkStatus.UNLINKED
    instance_id: UUID | None = None
    client_code: str | None = None
    client_name: str | None = None
    secret: str | None = None
    policy: SyncPolicy | None = None
    notices: list[CloudNotice] = field(default_factory=list[CloudNotice])
    linked_at: datetime | None = None
    last_heartbeat_ok_at: datetime | None = None
    last_attempt_at: datetime | None = None
    secret_rotated_at: datetime | None = None
    last_error_code: str | None = None
    consecutive_failures: int = 0

    @property
    def effective_policy(self) -> SyncPolicy:
        return self.policy or SyncPolicy()

    @property
    def has_credentials(self) -> bool:
        return self.instance_id is not None and bool(self.secret)

    def clear_link(self) -> None:
        """Olvida la vinculación pero conserva `pseudonym_key` e `install_id`."""
        self.status = LinkStatus.UNLINKED
        self.instance_id = None
        self.client_code = None
        self.client_name = None
        self.secret = None
        self.policy = None
        self.notices = []
        self.linked_at = None
        self.last_heartbeat_ok_at = None
        self.secret_rotated_at = None
        self.last_error_code = None
        self.consecutive_failures = 0
