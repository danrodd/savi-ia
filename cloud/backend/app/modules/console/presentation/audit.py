"""Auditoría append-only."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import transaction
from app.modules.audit.infrastructure import SqlAlchemyAuditRepository
from app.modules.console.presentation.common import (
    encode_cursor,
    parse_cursor,
)
from app.modules.console.presentation.schemas import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    AuditOut,
    AuditPage,
)
from app.modules.staff.application import Principal
from app.modules.staff.dependencies import RequirePermission
from app.modules.staff.domain import Permission

router = APIRouter()


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
    before = parse_cursor(cursor)
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
    next_cursor = encode_cursor(page[-1].occurred_at, page[-1].id) if len(rows) > limit else None
    return AuditPage(items=[AuditOut.of(e) for e in page], next_cursor=next_cursor)
