"""API de la consola (`/console/api`, §3 de la Fase 3).

Cada ruta declara `RequirePermission`; un test recorre el router y falla si falta alguna.
El frontend oculta lo que el backend igual rechaza.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_clock, transaction
from app.modules.audit.application import AuditRecorder
from app.modules.audit.domain import AuditEntry
from app.modules.audit.infrastructure import SqlAlchemyAuditRepository
from app.modules.clients.domain import ClientNotFound, ClientStatus, IdentityMode
from app.modules.clients.infrastructure import SqlAlchemyClientRepository
from app.modules.console.application import (
    ClientActions,
    InstanceActions,
    StaffActions,
    TokenActions,
)
from app.modules.console.queries import (
    ClientSummary,
    ConsoleQueries,
    HeartbeatItem,
    InstanceListItem,
)
from app.modules.enrollments.domain import EnrollmentToken
from app.modules.enrollments.infrastructure import SqlAlchemyEnrollmentTokenRepository
from app.modules.instances.domain import InstanceNotFound, InstanceRevoked
from app.modules.instances.infrastructure import SqlAlchemyInstanceRepository
from app.modules.staff.application import Principal
from app.modules.staff.dependencies import RequirePermission, build_auth_deps, request_context
from app.modules.staff.domain import Permission, Role, StaffUser, has_permission
from app.shared.clock import Clock
from app.shared.http_errors import ApiError

router = APIRouter(prefix="/console/api", tags=["console"])

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


# ------------------------------------------------------------------ utilidades


def _queries(request: Request, session: AsyncSession) -> ConsoleQueries:
    settings = request.app.state.settings
    return ConsoleQueries(session, get_clock(request), settings.latest_version)


def _audit(request: Request, session: AsyncSession) -> AuditRecorder:
    return AuditRecorder(SqlAlchemyAuditRepository(session), get_clock(request))


def _client_actions(request: Request, session: AsyncSession) -> ClientActions:
    clock: Clock = get_clock(request)
    return ClientActions(
        clients=SqlAlchemyClientRepository(session),
        instances=SqlAlchemyInstanceRepository(session),
        audit=_audit(request, session),
        clock=clock,
    )


def _instance_actions(request: Request, session: AsyncSession) -> InstanceActions:
    return InstanceActions(
        instances=SqlAlchemyInstanceRepository(session),
        audit=_audit(request, session),
        clock=get_clock(request),
    )


def _token_actions(request: Request, session: AsyncSession) -> TokenActions:
    return TokenActions(
        clients=SqlAlchemyClientRepository(session),
        tokens=SqlAlchemyEnrollmentTokenRepository(session),
        audit=_audit(request, session),
        clock=get_clock(request),
        default_expires_hours=request.app.state.settings.enrollment_token_ttl_hours,
    )


def _staff_actions(request: Request, session: AsyncSession) -> StaffActions:
    return StaffActions(build_auth_deps(request, session))


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _parse_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    """`<microsegundos desde epoch>_<uuid>`: seguro en una URL (sin `+` ni `:`)."""
    if not cursor:
        return None
    try:
        micros, _, ident = cursor.partition("_")
        return _EPOCH + timedelta(microseconds=int(micros)), UUID(ident)
    except ValueError as exc:
        raise ApiError(422, "validation_error", "El cursor no es válido.") from exc


def _cursor(at: datetime, ident: UUID) -> str:
    return f"{(at - _EPOCH) // timedelta(microseconds=1)}_{ident}"


async def _instance_item(queries: ConsoleQueries, instance_id: UUID) -> InstanceListItem:
    item = await queries.get_instance(instance_id)
    if item is None:
        raise InstanceNotFound("No existe la instancia.")
    return item


# ------------------------------------------------------------------ clientes


@router.get("/clients", response_model=ClientPage)
async def list_clients(
    request: Request,
    status: ClientStatus | None = None,
    q: str | None = Query(default=None, max_length=100),
    sort: Literal["code", "name", "last_seen"] = "code",
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    _: Principal = Depends(RequirePermission(Permission.CLIENTS_READ)),
) -> ClientPage:
    async with transaction(request) as session:
        items, total = await _queries(request, session).list_clients(
            status=status, q=q, sort=sort, limit=limit, offset=offset
        )
    return ClientPage(items=[ClientOut.of(s) for s in items], total=total)


@router.post("/clients", response_model=ClientOut, status_code=201)
async def create_client(
    body: ClientCreate,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_WRITE)),
) -> ClientOut:
    async with transaction(request) as session:
        client = await _client_actions(request, session).create(
            code=body.code,
            name=body.name,
            nit=body.nit,
            ctx=request_context(request, principal),
        )
        summary = await _queries(request, session).client_summary(client.id)
    assert summary is not None
    return ClientOut.of(summary)


async def _client_out(request: Request, session: AsyncSession, client_id: UUID) -> ClientOut:
    summary = await _queries(request, session).client_summary(client_id)
    if summary is None:
        raise ClientNotFound("No existe el cliente.")
    return ClientOut.of(summary)


@router.get("/clients/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: UUID,
    request: Request,
    _: Principal = Depends(RequirePermission(Permission.CLIENTS_READ)),
) -> ClientOut:
    async with transaction(request) as session:
        return await _client_out(request, session, client_id)


@router.patch("/clients/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: UUID,
    body: ClientPatch,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_WRITE)),
) -> ClientOut:
    async with transaction(request) as session:
        await _client_actions(request, session).update(
            client_id,
            name=body.name,
            nit=body.nit,
            nit_given="nit" in body.model_fields_set,
            ctx=request_context(request, principal),
        )
        return await _client_out(request, session, client_id)


@router.patch("/clients/{client_id}/policy", response_model=ClientOut)
async def set_client_policy(
    client_id: UUID,
    body: ClientPolicyPatch,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_POLICY)),
) -> ClientOut:
    async with transaction(request) as session:
        await _client_actions(request, session).set_policy(
            client_id,
            identity_mode=body.identity_mode,
            config_locked=body.config_locked,
            allow_local_cli=body.allow_local_cli,
            ctx=request_context(request, principal),
        )
        return await _client_out(request, session, client_id)


@router.post("/clients/{client_id}/suspend", response_model=ClientOut)
async def suspend_client(
    client_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_SUSPEND)),
) -> ClientOut:
    async with transaction(request) as session:
        await _client_actions(request, session).suspend(
            client_id, request_context(request, principal)
        )
        return await _client_out(request, session, client_id)


@router.post("/clients/{client_id}/activate", response_model=ClientOut)
async def activate_client(
    client_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_SUSPEND)),
) -> ClientOut:
    async with transaction(request) as session:
        await _client_actions(request, session).activate(
            client_id, request_context(request, principal)
        )
        return await _client_out(request, session, client_id)


# ------------------------------------------------------------------ instancias


@router.get("/instances", response_model=list[InstanceOut])
async def list_instances(
    request: Request,
    client_id: UUID | None = None,
    status: Literal["active", "suspended", "revoked"] | None = None,
    connectivity: Literal["online", "offline"] | None = None,
    version: str | None = Query(default=None, max_length=64),
    outdated: bool | None = None,
    principal: Principal = Depends(RequirePermission(Permission.INSTANCES_READ)),
) -> list[InstanceOut]:
    technical = has_permission(principal.user.role, Permission.INSTANCES_READ_TECHNICAL)
    async with transaction(request) as session:
        items = await _queries(request, session).list_instances(
            client_id=client_id,
            status=status,
            connectivity=connectivity,
            version=version,
            outdated=outdated,
        )
    return [InstanceOut.of(i, technical=technical) for i in items]


@router.get("/instances/{instance_id}", response_model=InstanceOut)
async def get_instance(
    instance_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.INSTANCES_READ)),
) -> InstanceOut:
    technical = has_permission(principal.user.role, Permission.INSTANCES_READ_TECHNICAL)
    async with transaction(request) as session:
        item = await _instance_item(_queries(request, session), instance_id)
    return InstanceOut.of(item, technical=technical)


@router.get("/instances/{instance_id}/heartbeats", response_model=HeartbeatPage)
async def list_heartbeats(
    instance_id: UUID,
    request: Request,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = None,
    _: Principal = Depends(RequirePermission(Permission.INSTANCES_READ_TECHNICAL)),
) -> HeartbeatPage:
    before = _parse_cursor(cursor)
    async with transaction(request) as session:
        queries = _queries(request, session)
        await _instance_item(queries, instance_id)
        rows: list[HeartbeatItem] = await queries.list_heartbeats(
            instance_id, limit=limit + 1, before=before
        )
    page = rows[:limit]
    next_cursor = _cursor(page[-1].received_at, page[-1].id) if len(rows) > limit else None
    return HeartbeatPage(
        items=[
            HeartbeatOut(id=str(h.id), received_at=h.received_at, payload=h.payload) for h in page
        ],
        next_cursor=next_cursor,
    )


async def _instance_action(
    request: Request,
    instance_id: UUID,
    principal: Principal,
    action: Literal["suspend", "activate", "revoke", "confirm_fingerprint", "request_rotation"],
) -> InstanceOut:
    try:
        async with transaction(request) as session:
            actions = _instance_actions(request, session)
            ctx = request_context(request, principal)
            await getattr(actions, action)(instance_id, ctx)
            item = await _instance_item(_queries(request, session), instance_id)
    except InstanceRevoked as exc:
        # Para la consola es un conflicto de estado: un 401 la haría creer que venció la sesión.
        raise ApiError(409, "instance_revoked", exc.message) from exc
    return InstanceOut.of(item, technical=True)


@router.post("/instances/{instance_id}/suspend", response_model=InstanceOut)
async def suspend_instance(
    instance_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.INSTANCES_MANAGE)),
) -> InstanceOut:
    return await _instance_action(request, instance_id, principal, "suspend")


@router.post("/instances/{instance_id}/activate", response_model=InstanceOut)
async def activate_instance(
    instance_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.INSTANCES_MANAGE)),
) -> InstanceOut:
    return await _instance_action(request, instance_id, principal, "activate")


@router.post("/instances/{instance_id}/revoke", response_model=InstanceOut)
async def revoke_instance(
    instance_id: UUID,
    body: RevokeBody,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.INSTANCES_MANAGE)),
) -> InstanceOut:
    if body.confirm != REVOKE_CONFIRMATION:
        raise ApiError(
            422, "confirmation_required", f'Para revocar escribí "{REVOKE_CONFIRMATION}".'
        )
    return await _instance_action(request, instance_id, principal, "revoke")


@router.post("/instances/{instance_id}/confirm-fingerprint", response_model=InstanceOut)
async def confirm_fingerprint(
    instance_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.INSTANCES_MANAGE)),
) -> InstanceOut:
    return await _instance_action(request, instance_id, principal, "confirm_fingerprint")


@router.post("/instances/{instance_id}/request-rotation", response_model=InstanceOut)
async def request_rotation(
    instance_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.INSTANCES_MANAGE)),
) -> InstanceOut:
    return await _instance_action(request, instance_id, principal, "request_rotation")


# ------------------------------------------------------------------ tokens de vinculación


@router.get("/clients/{client_id}/enrollment-tokens", response_model=list[TokenOut])
async def list_tokens(
    client_id: UUID,
    request: Request,
    _: Principal = Depends(RequirePermission(Permission.TOKENS_MANAGE)),
) -> list[TokenOut]:
    now = get_clock(request)()
    async with transaction(request) as session:
        tokens = await _token_actions(request, session).list(client_id)
    return [TokenOut.of(t, now) for t in tokens]


@router.post("/clients/{client_id}/enrollment-tokens", response_model=TokenCreated, status_code=201)
async def create_token(
    client_id: UUID,
    body: TokenCreate,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.TOKENS_MANAGE)),
) -> TokenCreated:
    async with transaction(request) as session:
        created = await _token_actions(request, session).create(
            client_id,
            expires_hours=body.expires_hours,
            created_by=principal.user.email,
            ctx=request_context(request, principal),
        )
    return TokenCreated(
        id=str(created.token.id), token=created.plaintext, expires_at=created.token.expires_at
    )


@router.delete("/enrollment-tokens/{token_id}", status_code=204)
async def revoke_token(
    token_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.TOKENS_MANAGE)),
) -> None:
    async with transaction(request) as session:
        await _token_actions(request, session).revoke(token_id, request_context(request, principal))


# ------------------------------------------------------------------ staff


@router.get("/staff", response_model=list[StaffOut])
async def list_staff(
    request: Request,
    _: Principal = Depends(RequirePermission(Permission.STAFF_MANAGE)),
) -> list[StaffOut]:
    async with transaction(request) as session:
        users = await build_auth_deps(request, session).users.list_all()
    return [StaffOut.of(u) for u in users]


@router.post("/staff", response_model=StaffCreated, status_code=201)
async def create_staff(
    body: StaffCreate,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.STAFF_MANAGE)),
) -> StaffCreated:
    async with transaction(request) as session:
        created = await _staff_actions(request, session).create(
            email=body.email,
            full_name=body.full_name,
            role=body.role,
            ctx=request_context(request, principal),
        )
    base = StaffOut.of(created.user)
    return StaffCreated(**base.model_dump(), temporary_password=created.temporary_password)


@router.patch("/staff/{staff_id}", response_model=StaffOut)
async def update_staff(
    staff_id: UUID,
    body: StaffPatch,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.STAFF_MANAGE)),
) -> StaffOut:
    async with transaction(request) as session:
        user = await _staff_actions(request, session).update(
            staff_id,
            full_name=body.full_name,
            role=body.role,
            ctx=request_context(request, principal),
        )
    return StaffOut.of(user)


@router.post("/staff/{staff_id}/deactivate", response_model=StaffOut)
async def deactivate_staff(
    staff_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.STAFF_MANAGE)),
) -> StaffOut:
    async with transaction(request) as session:
        user = await _staff_actions(request, session).deactivate(
            staff_id, request_context(request, principal)
        )
    return StaffOut.of(user)


@router.post("/staff/{staff_id}/activate", response_model=StaffOut)
async def activate_staff(
    staff_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.STAFF_MANAGE)),
) -> StaffOut:
    async with transaction(request) as session:
        user = await _staff_actions(request, session).activate(
            staff_id, request_context(request, principal)
        )
    return StaffOut.of(user)


@router.post("/staff/{staff_id}/reset-mfa", response_model=StaffOut)
async def reset_staff_mfa(
    staff_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.STAFF_MANAGE)),
) -> StaffOut:
    async with transaction(request) as session:
        user = await _staff_actions(request, session).reset_mfa(
            staff_id, request_context(request, principal)
        )
    return StaffOut.of(user)


# ------------------------------------------------------------------ auditoría


@router.get("/audit", response_model=AuditPage)
async def list_audit(
    request: Request,
    actor: str | None = Query(default=None, max_length=254),
    action: str | None = Query(default=None, max_length=64),
    target: str | None = Query(default=None, max_length=64),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = None,
    _: Principal = Depends(RequirePermission(Permission.AUDIT_READ)),
) -> AuditPage:
    before = _parse_cursor(cursor)
    async with transaction(request) as session:
        rows = await SqlAlchemyAuditRepository(session).list(
            actor=actor,
            action=action,
            target=target,
            start=start,
            end=end,
            limit=limit + 1,
            before_id=before,
        )
    page = rows[:limit]
    next_cursor = _cursor(page[-1].occurred_at, page[-1].id) if len(rows) > limit else None
    return AuditPage(items=[AuditOut.of(e) for e in page], next_cursor=next_cursor)
