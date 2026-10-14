"""Staff de SAVI Cloud: roles, matriz de permisos (§1) y puertos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.shared.errors import DomainError


class Role(StrEnum):
    ADMIN = "admin"
    SOPORTE = "soporte"
    COMERCIAL = "comercial"


class Permission(StrEnum):
    OVERVIEW_READ = "overview.read"
    CLIENTS_READ = "clients.read"
    CLIENTS_WRITE = "clients.write"
    CLIENTS_SUSPEND = "clients.suspend"
    # Identidad de las personas y bloqueo de configuración: decisiones de privacidad y de
    # seguridad de un cliente, solo del administrador.
    CLIENTS_POLICY = "clients.policy"
    # Plan, vigencia y movimientos de un cliente: lo gestiona quien lo atiende comercialmente.
    CLIENTS_BILLING = "clients.billing"
    INSTANCES_READ = "instances.read"
    INSTANCES_READ_TECHNICAL = "instances.read_technical"
    INSTANCES_MANAGE = "instances.manage"
    TOKENS_MANAGE = "tokens.manage"
    ALERTS_READ = "alerts.read"
    ALERTS_MANAGE = "alerts.manage"
    ALERTS_CONFIGURE = "alerts.configure"
    STAFF_MANAGE = "staff.manage"
    AUDIT_READ = "audit.read"


_ALL = frozenset(Role)
_ADMIN = frozenset({Role.ADMIN})
_ADMIN_SOPORTE = frozenset({Role.ADMIN, Role.SOPORTE})
_ADMIN_COMERCIAL = frozenset({Role.ADMIN, Role.COMERCIAL})

# Única fuente de verdad de la matriz. El frontend solo oculta lo que esto ya rechaza.
PERMISSIONS: dict[Permission, frozenset[Role]] = {
    Permission.OVERVIEW_READ: _ALL,
    Permission.CLIENTS_READ: _ALL,
    Permission.CLIENTS_WRITE: _ADMIN_COMERCIAL,
    Permission.CLIENTS_SUSPEND: _ADMIN,
    Permission.CLIENTS_POLICY: _ADMIN,
    Permission.CLIENTS_BILLING: _ADMIN_COMERCIAL,
    Permission.INSTANCES_READ: _ALL,
    Permission.INSTANCES_READ_TECHNICAL: _ADMIN_SOPORTE,
    Permission.INSTANCES_MANAGE: _ADMIN_SOPORTE,
    Permission.TOKENS_MANAGE: _ADMIN_SOPORTE,
    Permission.ALERTS_READ: _ALL,
    Permission.ALERTS_MANAGE: _ADMIN_SOPORTE,
    Permission.ALERTS_CONFIGURE: _ADMIN,
    Permission.STAFF_MANAGE: _ADMIN,
    Permission.AUDIT_READ: _ADMIN,
}


def has_permission(role: Role, permission: Permission) -> bool:
    return role in PERMISSIONS[permission]


def permissions_of(role: Role) -> list[Permission]:
    return [p for p in Permission if has_permission(role, p)]


@dataclass(frozen=True)
class StaffUser:
    id: UUID
    email: str
    full_name: str
    password_hash: str
    role: Role
    is_active: bool
    must_change_password: bool
    failed_attempts: int
    created_at: datetime
    updated_at: datetime
    totp_secret_encrypted: str | None = None
    totp_enabled_at: datetime | None = None
    totp_last_step: int = 0
    locked_until: datetime | None = None
    last_login_at: datetime | None = None

    @property
    def totp_enabled(self) -> bool:
        return self.totp_enabled_at is not None and self.totp_secret_encrypted is not None


@dataclass(frozen=True)
class StaffSession:
    jti: UUID
    staff_user_id: UUID
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    ip: str | None = None
    user_agent: str | None = None


class InvalidCredentials(DomainError):
    """Email inexistente, contraseña mala, cuenta bloqueada o inactiva: un solo código."""

    code = "invalid_credentials"


class InvalidMfaCode(DomainError):
    code = "invalid_mfa_code"


class InvalidSessionToken(DomainError):
    code = "invalid_session_token"


class WeakPassword(DomainError):
    code = "weak_password"


class InvalidStaffData(DomainError):
    code = "invalid_staff_data"


class StaffEmailAlreadyExists(DomainError):
    code = "staff_email_already_exists"


class StaffNotFound(DomainError):
    code = "staff_not_found"


class LastAdminProtected(DomainError):
    code = "last_admin_protected"


class StaffRepository(Protocol):
    async def add(self, user: StaffUser) -> None:
        """Persiste. Levanta `StaffEmailAlreadyExists` si el email ya existe."""
        ...

    async def get_by_id(self, user_id: UUID) -> StaffUser | None: ...

    async def get_by_email(self, email: str) -> StaffUser | None: ...

    async def list_all(self) -> list[StaffUser]: ...

    async def save(self, user: StaffUser) -> None: ...

    async def count_active_admins(self) -> int: ...


class SessionRepository(Protocol):
    async def add(self, session: StaffSession) -> None: ...

    async def get(self, jti: UUID) -> StaffSession | None: ...

    async def revoke(self, jti: UUID, at: datetime) -> None: ...

    async def revoke_all_of_user(self, user_id: UUID, at: datetime) -> int: ...
