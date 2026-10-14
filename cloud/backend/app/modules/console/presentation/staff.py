"""Personal de SEO que usa la consola."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.dependencies import transaction
from app.modules.console.presentation.common import (
    make_staff_actions,
)
from app.modules.console.presentation.schemas import (
    StaffCreate,
    StaffCreated,
    StaffOut,
    StaffPatch,
)
from app.modules.staff.application import Principal
from app.modules.staff.dependencies import RequirePermission, build_auth_deps, request_context
from app.modules.staff.domain import Permission

router = APIRouter()


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
        created = await make_staff_actions(request, session).create(
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
        user = await make_staff_actions(request, session).update(
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
        user = await make_staff_actions(request, session).deactivate(
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
        user = await make_staff_actions(request, session).activate(
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
        user = await make_staff_actions(request, session).reset_mfa(
            staff_id, request_context(request, principal)
        )
    return StaffOut.of(user)
