"""Plan, vigencia y movimientos de un cliente (`/console/api/clients/{id}/...`)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import get_clock, transaction
from app.modules.alerts.runner import bogota_today
from app.modules.clients.domain import ClientNotFound
from app.modules.clients.infrastructure import (
    SqlAlchemyClientRepository,
    SqlAlchemyLedgerRepository,
)
from app.modules.clients.subscription import LedgerEntry, LedgerKind, Subscription
from app.modules.console.presentation.common import make_client_actions
from app.modules.console.presentation.schemas import (
    LedgerEntryBody,
    LedgerEntryOut,
    SubscriptionBody,
    SubscriptionOut,
)
from app.modules.staff.application import Principal
from app.modules.staff.dependencies import RequirePermission, request_context
from app.modules.staff.domain import Permission

router = APIRouter()

# Con cuántos días de anticipación se muestra «por vencer» (la alerta tiene su propio umbral).
WARN_DAYS = 7


def _out(entry: LedgerEntry) -> LedgerEntryOut:
    return LedgerEntryOut(
        id=str(entry.id),
        kind=entry.kind.value,
        amount_usd=str(entry.amount_usd),
        note=entry.note,
        extends_until=entry.extends_until,
        created_by=entry.created_by,
        created_at=entry.created_at,
    )


def _subscription_out(sub: Subscription, today: date) -> SubscriptionOut:
    days_left = (sub.valid_until - today).days if sub.valid_until else None
    return SubscriptionOut(
        **sub.to_json(),  # type: ignore[arg-type]
        status=sub.status(today, warn_days=WARN_DAYS).value,
        days_left=days_left,
    )


@router.get("/clients/{client_id}/subscription", response_model=SubscriptionOut)
async def get_subscription(
    client_id: UUID,
    request: Request,
    _: Principal = Depends(RequirePermission(Permission.CLIENTS_BILLING)),
) -> SubscriptionOut:
    async with transaction(request) as session:
        client = await SqlAlchemyClientRepository(session).get_by_id(client_id)
    if client is None:
        raise ClientNotFound("No existe el cliente.")
    return _subscription_out(client.subscription, bogota_today(get_clock(request)()))


@router.put("/clients/{client_id}/subscription", response_model=SubscriptionOut)
async def set_subscription(
    client_id: UUID,
    body: SubscriptionBody,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_BILLING)),
) -> SubscriptionOut:
    subscription = Subscription.build(
        plan_name=body.plan_name,
        monthly_fee_usd=body.monthly_fee_usd,
        max_users=body.max_users,
        valid_until=body.valid_until,
        notes=body.notes,
    )
    async with transaction(request) as session:
        client = await make_client_actions(request, session).set_subscription(
            client_id, subscription, ctx=request_context(request, principal)
        )
    return _subscription_out(client.subscription, bogota_today(get_clock(request)()))


@router.get("/clients/{client_id}/ledger", response_model=list[LedgerEntryOut])
async def list_ledger(
    client_id: UUID,
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
    _: Principal = Depends(RequirePermission(Permission.CLIENTS_BILLING)),
) -> list[LedgerEntryOut]:
    async with transaction(request) as session:
        if await SqlAlchemyClientRepository(session).get_by_id(client_id) is None:
            raise ClientNotFound("No existe el cliente.")
        entries = await SqlAlchemyLedgerRepository(session).list_by_client(client_id, limit=limit)
    return [_out(e) for e in entries]


@router.post("/clients/{client_id}/ledger", response_model=LedgerEntryOut, status_code=201)
async def record_ledger_entry(
    client_id: UUID,
    body: LedgerEntryBody,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.CLIENTS_BILLING)),
) -> LedgerEntryOut:
    async with transaction(request) as session:
        entry = await make_client_actions(request, session).record_ledger_entry(
            client_id,
            kind=LedgerKind(body.kind),
            amount_usd=body.amount_usd,
            note=body.note,
            extends_until=body.extends_until,
            ctx=request_context(request, principal),
        )
    return _out(entry)
