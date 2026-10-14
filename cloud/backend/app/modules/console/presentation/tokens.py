"""Tokens de vinculación de un cliente."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_clock, transaction
from app.modules.console.presentation.common import (
    make_token_actions,
)
from app.modules.console.presentation.schemas import (
    TokenCreate,
    TokenCreated,
    TokenOut,
)
from app.modules.staff.application import Principal
from app.modules.staff.dependencies import RequirePermission, request_context
from app.modules.staff.domain import Permission

router = APIRouter()


# ------------------------------------------------------------------ tokens de vinculación


@router.get("/clients/{client_id}/enrollment-tokens", response_model=list[TokenOut])
async def list_tokens(
    client_id: UUID,
    request: Request,
    _: Principal = Depends(RequirePermission(Permission.TOKENS_MANAGE)),
) -> list[TokenOut]:
    now = get_clock(request)()
    async with transaction(request) as session:
        tokens = await make_token_actions(request, session).list(client_id)
    return [TokenOut.of(t, now) for t in tokens]


@router.post("/clients/{client_id}/enrollment-tokens", response_model=TokenCreated, status_code=201)
async def create_token(
    client_id: UUID,
    body: TokenCreate,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.TOKENS_MANAGE)),
) -> TokenCreated:
    async with transaction(request) as session:
        created = await make_token_actions(request, session).create(
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
        await make_token_actions(request, session).revoke(
            token_id, request_context(request, principal)
        )
