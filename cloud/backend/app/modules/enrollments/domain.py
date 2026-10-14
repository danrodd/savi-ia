from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.shared.errors import DomainError


class TokenState(StrEnum):
    PENDING = "pending"
    USED = "used"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True)
class EnrollmentToken:
    """Token de vinculación. Solo existe su hash; el texto plano no se persiste."""

    id: UUID
    client_id: UUID
    token_hash: bytes
    expires_at: datetime
    created_at: datetime
    created_by: str
    used_at: datetime | None = None
    used_by_instance_id: UUID | None = None
    revoked_at: datetime | None = None

    def state(self, now: datetime) -> TokenState:
        if self.used_at is not None:
            return TokenState.USED
        if self.revoked_at is not None:
            return TokenState.REVOKED
        if now >= self.expires_at:
            return TokenState.EXPIRED
        return TokenState.PENDING

    def is_redeemable(self, now: datetime) -> bool:
        return self.state(now) is TokenState.PENDING


@dataclass(frozen=True)
class InstanceInfo:
    """Datos que la instancia declara al canjear (§3.1 del contrato)."""

    name: str
    deployment_mode: str
    version: str | None
    commit: str | None
    os: str
    agent_db_engine: str
    fingerprint: str


class InvalidExpiration(DomainError):
    code = "invalid_expiration"


class EnrollmentTokenInvalid(DomainError):
    """Inexistente, vencido, usado o revocado: un solo código para no revelar cuál."""

    code = "enrollment_token_invalid"


class EnrollmentTokenNotFound(DomainError):
    code = "enrollment_token_not_found"


class EnrollmentTokenAlreadyUsed(DomainError):
    code = "enrollment_token_already_used"


class EnrollmentTokenRepository(Protocol):
    async def add(self, token: EnrollmentToken) -> None: ...

    async def get_by_id(self, token_id: UUID) -> EnrollmentToken | None: ...

    async def get_by_hash_for_update(self, token_hash: bytes) -> EnrollmentToken | None:
        """Busca por hash bloqueando la fila (`SELECT ... FOR UPDATE`)."""
        ...

    async def list_by_client(self, client_id: UUID) -> list[EnrollmentToken]: ...

    async def save(self, token: EnrollmentToken) -> None:
        """Persiste los campos mutables: `used_at`, `used_by_instance_id`, `revoked_at`."""
        ...
