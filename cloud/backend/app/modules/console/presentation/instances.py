"""Rutas de instancias y sus acciones."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import transaction
from app.modules.console.presentation.common import (
    encode_cursor,
    instance_item,
    make_instance_actions,
    make_queries,
    parse_cursor,
)
from app.modules.console.presentation.schemas import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    REVOKE_CONFIRMATION,
    HeartbeatOut,
    HeartbeatPage,
    InstanceOut,
    RevokeBody,
)
from app.modules.console.queries import (
    HeartbeatItem,
)
from app.modules.instances.domain import InstanceRevoked
from app.modules.staff.application import Principal
from app.modules.staff.dependencies import RequirePermission, request_context
from app.modules.staff.domain import Permission, has_permission
from app.shared.http_errors import ApiError

router = APIRouter()


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
        items = await make_queries(request, session).list_instances(
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
        item = await instance_item(make_queries(request, session), instance_id)
    return InstanceOut.of(item, technical=technical)


@router.get("/instances/{instance_id}/heartbeats", response_model=HeartbeatPage)
async def list_heartbeats(
    instance_id: UUID,
    request: Request,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = None,
    _: Principal = Depends(RequirePermission(Permission.INSTANCES_READ_TECHNICAL)),
) -> HeartbeatPage:
    before = parse_cursor(cursor)
    async with transaction(request) as session:
        queries = make_queries(request, session)
        await instance_item(queries, instance_id)
        rows: list[HeartbeatItem] = await queries.list_heartbeats(
            instance_id, limit=limit + 1, before=before
        )
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1].received_at, page[-1].id) if len(rows) > limit else None
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
            actions = make_instance_actions(request, session)
            ctx = request_context(request, principal)
            await getattr(actions, action)(instance_id, ctx)
            item = await instance_item(make_queries(request, session), instance_id)
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
