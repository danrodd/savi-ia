"""Rutas de alertas de la consola (§3.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_clock, transaction
from app.modules.alerts.application import AlertActions, load_rule_configs
from app.modules.alerts.domain import Alert, AlertStatus, RuleConfig, Severity
from app.modules.alerts.infrastructure import (
    SqlAlchemyAlertRepository,
    SqlAlchemyAlertRuleRepository,
)
from app.modules.audit.application import AuditRecorder
from app.modules.audit.infrastructure import SqlAlchemyAuditRepository
from app.modules.clients.infrastructure import ClientModel
from app.modules.staff.application import Principal
from app.modules.staff.dependencies import RequirePermission, request_context
from app.modules.staff.domain import Permission

router = APIRouter(prefix="/console/api", tags=["console-alerts"])

MAX_LIMIT = 200


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AlertOut(BaseModel):
    id: str
    rule_code: str
    severity: str
    status: str
    client_id: str
    # Nombre del cliente, para no mostrar solo un enlace; `None` si ya no existe.
    client_name: str | None = None
    instance_id: str | None
    details: dict[str, Any]
    opened_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    resolved_at: datetime | None
    resolved_by: str | None
    resolution_note: str | None

    @classmethod
    def of(cls, a: Alert, client_name: str | None = None) -> AlertOut:
        return cls(
            id=str(a.id),
            rule_code=a.rule_code,
            severity=a.severity.value,
            status=a.status.value,
            client_id=str(a.client_id),
            client_name=client_name,
            instance_id=str(a.instance_id) if a.instance_id else None,
            details=a.details,
            opened_at=a.opened_at,
            acknowledged_at=a.acknowledged_at,
            acknowledged_by=a.acknowledged_by,
            resolved_at=a.resolved_at,
            resolved_by=a.resolved_by,
            resolution_note=a.resolution_note,
        )


class RuleOut(BaseModel):
    code: str
    title: str
    description: str
    enabled: bool
    severity: str
    threshold: float | None
    threshold_unit: str | None
    default_threshold: float | None
    auto_resolve: bool

    @classmethod
    def of(cls, c: RuleConfig) -> RuleOut:
        d = c.definition
        return cls(
            code=d.code,
            title=d.title,
            description=d.description,
            enabled=c.enabled,
            severity=c.severity.value,
            threshold=c.threshold,
            threshold_unit=d.threshold_unit,
            default_threshold=d.threshold,
            auto_resolve=d.auto_resolve,
        )


class ResolveBody(_Body):
    note: str = Field(default="", max_length=500)


class RulePatch(_Body):
    enabled: bool | None = None
    threshold: float | None = None
    severity: Severity | None = None


def _actions(request: Request, session: AsyncSession) -> AlertActions:
    clock = get_clock(request)
    return AlertActions(
        alerts=SqlAlchemyAlertRepository(session),
        rules=SqlAlchemyAlertRuleRepository(session),
        audit=AuditRecorder(SqlAlchemyAuditRepository(session), clock),
        clock=clock,
    )


async def _client_names(session: AsyncSession, alerts: list[Alert]) -> dict[UUID, str]:
    ids = {a.client_id for a in alerts}
    if not ids:
        return {}
    rows = await session.execute(
        select(ClientModel.id, ClientModel.name).where(ClientModel.id.in_(ids))
    )
    return {cid: str(name) for cid, name in rows.all()}


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    request: Request,
    status: AlertStatus | None = None,
    severity: Severity | None = None,
    client_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    _: Principal = Depends(RequirePermission(Permission.ALERTS_READ)),
) -> list[AlertOut]:
    async with transaction(request) as session:
        rows = await SqlAlchemyAlertRepository(session).list(
            status=status, severity=severity, client_id=client_id, limit=limit
        )
        names = await _client_names(session, rows)
    return [AlertOut.of(a, names.get(a.client_id)) for a in rows]


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
async def acknowledge_alert(
    alert_id: UUID,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.ALERTS_MANAGE)),
) -> AlertOut:
    async with transaction(request) as session:
        alert = await _actions(request, session).acknowledge(
            alert_id, request_context(request, principal)
        )
        names = await _client_names(session, [alert])
    return AlertOut.of(alert, names.get(alert.client_id))


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut)
async def resolve_alert(
    alert_id: UUID,
    body: ResolveBody,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.ALERTS_MANAGE)),
) -> AlertOut:
    async with transaction(request) as session:
        alert = await _actions(request, session).resolve(
            alert_id, body.note, request_context(request, principal)
        )
        names = await _client_names(session, [alert])
    return AlertOut.of(alert, names.get(alert.client_id))


@router.get("/alert-rules", response_model=list[RuleOut])
async def list_rules(
    request: Request,
    _: Principal = Depends(RequirePermission(Permission.ALERTS_READ)),
) -> list[RuleOut]:
    async with transaction(request) as session:
        configs = await load_rule_configs(SqlAlchemyAlertRuleRepository(session))
    return [RuleOut.of(c) for c in configs]


@router.patch("/alert-rules/{code}", response_model=RuleOut)
async def update_rule(
    code: str,
    body: RulePatch,
    request: Request,
    principal: Principal = Depends(RequirePermission(Permission.ALERTS_CONFIGURE)),
) -> RuleOut:
    async with transaction(request) as session:
        updated = await _actions(request, session).configure_rule(
            code,
            enabled=body.enabled,
            threshold=body.threshold,
            threshold_given="threshold" in body.model_fields_set,
            severity=body.severity,
            ctx=request_context(request, principal),
        )
    return RuleOut.of(updated)
