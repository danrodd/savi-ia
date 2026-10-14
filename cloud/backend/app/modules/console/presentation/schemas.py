"""Modelos de entrada y salida de la API de la consola."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.audit.domain import AuditEntry
from app.modules.clients.domain import (
    IdentityMode,
)
from app.modules.console.queries import (
    ClientSummary,
    InstanceListItem,
)
from app.modules.enrollments.domain import EnrollmentToken
from app.modules.staff.domain import Role, StaffUser

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
REVOKE_CONFIRMATION = "REVOCAR"


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ modelos de respuesta


class ClientOut(BaseModel):
    id: str
    code: str
    name: str
    nit: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    instances_total: int
    instances_online: int
    last_seen_at: datetime | None
    oldest_version: str | None
    identity_mode: str
    config_locked: bool
    allow_local_cli: bool
    ai_policy: dict[str, Any]
    access_policy: dict[str, Any]

    @classmethod
    def of(cls, summary: ClientSummary) -> ClientOut:
        c = summary.client
        return cls(
            id=str(c.id),
            code=c.code,
            name=c.name,
            nit=c.nit,
            status=c.status.value,
            created_at=c.created_at,
            updated_at=c.updated_at,
            instances_total=summary.instances_total,
            instances_online=summary.instances_online,
            last_seen_at=summary.last_seen_at,
            oldest_version=summary.oldest_version,
            identity_mode=c.identity_mode.value,
            config_locked=c.config_locked,
            allow_local_cli=c.allow_local_cli,
            ai_policy=c.ai_policy.to_json(),
            access_policy=c.access_policy.to_json(),
        )


class ClientPage(BaseModel):
    items: list[ClientOut]
    total: int


class InstanceOut(BaseModel):
    id: str
    client_id: str
    client_code: str
    client_name: str
    name: str
    deployment_mode: str
    os: str
    agent_db_engine: str
    version: str | None
    commit: str | None
    status: str
    online: bool
    outdated: bool
    enrolled_at: datetime
    last_seen_at: datetime | None
    # Solo con `instances.read_technical`:
    status_reason: str | None = None
    fingerprint: str | None = None
    clock_skew_seconds: int | None = None
    rotation_requested_at: datetime | None = None
    last_heartbeat: dict[str, Any] | None = None

    @classmethod
    def of(cls, item: InstanceListItem, *, technical: bool) -> InstanceOut:
        i = item.instance
        out = cls(
            id=str(i.id),
            client_id=str(i.client_id),
            client_code=item.client_code,
            client_name=item.client_name,
            name=i.name,
            deployment_mode=i.deployment_mode,
            os=i.os,
            agent_db_engine=i.agent_db_engine,
            version=i.version,
            commit=i.commit,
            status=i.status.value,
            online=item.online,
            outdated=item.outdated,
            enrolled_at=i.enrolled_at,
            last_seen_at=i.last_seen_at,
        )
        if technical:
            out.status_reason = i.status_reason
            out.fingerprint = i.fingerprint
            out.clock_skew_seconds = i.clock_skew_seconds
            out.rotation_requested_at = i.rotation_requested_at
            out.last_heartbeat = i.last_heartbeat
        return out


class HeartbeatOut(BaseModel):
    id: str
    received_at: datetime
    payload: dict[str, Any]


class HeartbeatPage(BaseModel):
    items: list[HeartbeatOut]
    next_cursor: str | None


class TokenOut(BaseModel):
    id: str
    state: str
    expires_at: datetime
    created_at: datetime
    created_by: str
    used_at: datetime | None
    used_by_instance_id: str | None
    revoked_at: datetime | None

    @classmethod
    def of(cls, token: EnrollmentToken, now: datetime) -> TokenOut:
        # Nunca el token: de él solo se guarda el hash.
        return cls(
            id=str(token.id),
            state=token.state(now).value,
            expires_at=token.expires_at,
            created_at=token.created_at,
            created_by=token.created_by,
            used_at=token.used_at,
            used_by_instance_id=str(token.used_by_instance_id)
            if token.used_by_instance_id
            else None,
            revoked_at=token.revoked_at,
        )


class TokenCreated(BaseModel):
    id: str
    token: str  # única vez que se ve
    expires_at: datetime


class StaffOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    mfa_enabled: bool
    last_login_at: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, user: StaffUser) -> StaffOut:
        return cls(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
            mfa_enabled=user.totp_enabled,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )


class StaffCreated(StaffOut):
    temporary_password: str  # única vez que se ve


class AuditOut(BaseModel):
    id: str
    occurred_at: datetime
    actor_email: str | None
    action: str
    target_type: str | None
    target_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None

    @classmethod
    def of(cls, e: AuditEntry) -> AuditOut:
        return cls(
            id=str(e.id),
            occurred_at=e.occurred_at,
            actor_email=e.actor_email,
            action=e.action,
            target_type=e.target_type,
            target_id=e.target_id,
            before=e.before,
            after=e.after,
            ip=e.ip,
        )


class AuditPage(BaseModel):
    items: list[AuditOut]
    next_cursor: str | None


# ------------------------------------------------------------------ cuerpos de entrada


class ClientCreate(_Body):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    nit: str | None = Field(default=None, max_length=32)


class ClientPatch(_Body):
    name: str | None = Field(default=None, max_length=200)
    nit: str | None = Field(default=None, max_length=32)


_Usd = Annotated[Decimal, Field(ge=0, le=99999999, max_digits=12, decimal_places=4)]
_Provider = Literal["claude", "gemini", "openai"]


class AiPolicyBody(_Body):
    allowed_providers: list[_Provider] | None = None
    user_monthly_usd: _Usd | None = None
    provider_monthly_usd: dict[_Provider, _Usd] = Field(default_factory=dict[_Provider, _Usd])
    user_overrides: dict[str, _Usd] = Field(default_factory=dict[str, _Usd], max_length=500)


class AccessGroupBody(_Body):
    # Vacío al crear: Cloud le asigna uno. Al editar se conserva.
    id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    members: list[str] = Field(default_factory=list[str], max_length=500)
    databases: list[str] = Field(default_factory=list[str], max_length=200)


class AccessPolicyBody(_Body):
    default_databases: list[str] | None = Field(default=None, max_length=200)
    user_databases: dict[str, list[str]] = Field(
        default_factory=dict[str, list[str]], max_length=500
    )
    groups: list[AccessGroupBody] = Field(default_factory=list[AccessGroupBody], max_length=50)


class ClientPolicyPatch(_Body):
    identity_mode: IdentityMode | None = None
    config_locked: bool | None = None
    allow_local_cli: bool | None = None


class RevokeBody(_Body):
    confirm: str


class TokenCreate(_Body):
    expires_hours: int = Field(default=72, ge=1, le=168)


class StaffCreate(_Body):
    email: str = Field(min_length=3, max_length=254)
    full_name: str = Field(min_length=1, max_length=200)
    role: Role


class StaffPatch(_Body):
    full_name: str | None = Field(default=None, max_length=200)
    role: Role | None = None
