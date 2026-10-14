"""Rutas de clientes y su política (`/console/api/clients`)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import transaction
from app.modules.clients.domain import (
    ClientStatus,
)
from app.modules.clients.policies import AccessPolicy, AiPolicy
from app.modules.console.presentation.common import (
    client_out,
    make_client_actions,
    make_queries,
)
from app.modules.console.presentation.schemas import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    AccessPolicyBody,
    AiPolicyBody,
    ClientCreate,
    ClientOut,
    ClientPage,
    ClientPatch,
    ClientPolicyPatch,
)
from app.modules.staff.application import Principal
from app.modules.staff.dependencies import RequirePermission, request_context
from app.modules.staff.domain import Permission

router = APIRouter()


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
        items, total = await make_queries(request, session).list_clients(
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
        client = await make_client_actions(request, session).create(
            code=body.code,
            name=body.name,
            nit=body.nit,
            ctx=request_context(request, principal),
        )
        summary = await make_queries(request, session).client_summary(client.id)
    assert summary is not None
    return ClientOut.of(summary)


@router.get("/clients/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: UUID,
    request: Request,
    _: Principal = Depends(RequirePermission(Permission.CLIENTS_READ)),
) -> ClientOut:
    async with transaction(request) as session:
        return await client_out(request, session, client_id)


@router.patch("/clients/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: UUID,
    body: ClientPatch,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_WRITE)),
) -> ClientOut:
    async with transaction(request) as session:
        await make_client_actions(request, session).update(
            client_id,
            name=body.name,
            nit=body.nit,
            nit_given="nit" in body.model_fields_set,
            ctx=request_context(request, principal),
        )
        return await client_out(request, session, client_id)


@router.patch("/clients/{client_id}/policy", response_model=ClientOut)
async def set_client_policy(
    client_id: UUID,
    body: ClientPolicyPatch,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_POLICY)),
) -> ClientOut:
    async with transaction(request) as session:
        await make_client_actions(request, session).set_policy(
            client_id,
            identity_mode=body.identity_mode,
            config_locked=body.config_locked,
            allow_local_cli=body.allow_local_cli,
            ctx=request_context(request, principal),
        )
        return await client_out(request, session, client_id)


@router.put("/clients/{client_id}/ai-policy", response_model=ClientOut)
async def set_client_ai_policy(
    client_id: UUID,
    body: AiPolicyBody,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_POLICY)),
) -> ClientOut:
    policy = AiPolicy.build(
        allowed_providers=body.allowed_providers,
        user_monthly_usd=body.user_monthly_usd,
        provider_monthly_usd={str(k): v for k, v in body.provider_monthly_usd.items()},
        user_overrides=dict(body.user_overrides),
    )
    async with transaction(request) as session:
        await make_client_actions(request, session).set_ai_policy(
            client_id, policy, ctx=request_context(request, principal)
        )
        return await client_out(request, session, client_id)


@router.put("/clients/{client_id}/access-policy", response_model=ClientOut)
async def set_client_access_policy(
    client_id: UUID,
    body: AccessPolicyBody,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_POLICY)),
) -> ClientOut:
    policy = AccessPolicy.build(
        default_databases=body.default_databases,
        user_databases=body.user_databases,
        groups=[g.model_dump() for g in body.groups],
    )
    async with transaction(request) as session:
        await make_client_actions(request, session).set_access_policy(
            client_id, policy, ctx=request_context(request, principal)
        )
        return await client_out(request, session, client_id)


@router.post("/clients/{client_id}/suspend", response_model=ClientOut)
async def suspend_client(
    client_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_SUSPEND)),
) -> ClientOut:
    async with transaction(request) as session:
        await make_client_actions(request, session).suspend(
            client_id, request_context(request, principal)
        )
        return await client_out(request, session, client_id)


@router.post("/clients/{client_id}/activate", response_model=ClientOut)
async def activate_client(
    client_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_SUSPEND)),
) -> ClientOut:
    async with transaction(request) as session:
        await make_client_actions(request, session).activate(
            client_id, request_context(request, principal)
        )
        return await client_out(request, session, client_id)
