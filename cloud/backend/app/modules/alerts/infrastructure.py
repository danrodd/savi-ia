from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    String,
    Text,
    Uuid,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.alerts.domain import LIVE_STATUSES, Alert, AlertStatus, Severity
from app.shared.clock import as_utc

JsonType = JSON().with_variant(JSONB(), "postgresql")
_LIVE_SQL = "status in ('open', 'acknowledged')"


class AlertModel(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("status in ('open', 'acknowledged', 'resolved')", name="status_valid"),
        CheckConstraint("severity in ('info', 'warning', 'critical')", name="severity_valid"),
        # Nunca dos alertas vivas idénticas (§5.2): lo garantiza la base, no solo el motor.
        Index(
            "uq_alerts_dedup_key_live",
            "dedup_key",
            unique=True,
            postgresql_where=text(_LIVE_SQL),
            sqlite_where=text(_LIVE_SQL),
        ),
        Index("ix_alerts_status_opened_at", "status", "opened_at"),
        Index("ix_alerts_client_id", "client_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    instance_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AlertRuleModel(Base):
    """Ajustes que el administrador cambió; lo que no está acá usa el valor por defecto."""

    __tablename__ = "alert_rules"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)


def _opt(value: datetime | None) -> datetime | None:
    return as_utc(value) if value else None


def to_entity(m: AlertModel) -> Alert:
    return Alert(
        id=m.id,
        rule_code=m.rule_code,
        severity=Severity(m.severity),
        client_id=m.client_id,
        instance_id=m.instance_id,
        status=AlertStatus(m.status),
        details=m.details,
        opened_at=as_utc(m.opened_at),
        dedup_key=m.dedup_key,
        acknowledged_at=_opt(m.acknowledged_at),
        acknowledged_by=m.acknowledged_by,
        resolved_at=_opt(m.resolved_at),
        resolved_by=m.resolved_by,
        resolution_note=m.resolution_note,
    )


class SqlAlchemyAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, alert: Alert) -> None:
        self._session.add(
            AlertModel(
                id=alert.id,
                rule_code=alert.rule_code,
                severity=alert.severity.value,
                client_id=alert.client_id,
                instance_id=alert.instance_id,
                status=alert.status.value,
                dedup_key=alert.dedup_key,
                details=alert.details,
                opened_at=alert.opened_at,
            )
        )
        await self._session.flush()

    async def get(self, alert_id: UUID) -> Alert | None:
        model = await self._session.get(AlertModel, alert_id)
        return to_entity(model) if model else None

    async def save(self, alert: Alert) -> None:
        model = await self._session.get(AlertModel, alert.id)
        if model is None:
            raise LookupError(f"Alerta {alert.id} no existe")
        model.severity = alert.severity.value
        model.status = alert.status.value
        model.details = alert.details
        model.acknowledged_at = alert.acknowledged_at
        model.acknowledged_by = alert.acknowledged_by
        model.resolved_at = alert.resolved_at
        model.resolved_by = alert.resolved_by
        model.resolution_note = alert.resolution_note
        await self._session.flush()

    async def list_live(self) -> list[Alert]:
        stmt = select(AlertModel).where(AlertModel.status.in_([s.value for s in LIVE_STATUSES]))
        return [to_entity(m) for m in (await self._session.execute(stmt)).scalars()]

    async def list(
        self,
        *,
        status: AlertStatus | None,
        severity: Severity | None,
        client_id: UUID | None,
        limit: int,
    ) -> list[Alert]:
        stmt = select(AlertModel)
        if status is not None:
            stmt = stmt.where(AlertModel.status == status.value)
        if severity is not None:
            stmt = stmt.where(AlertModel.severity == severity.value)
        if client_id is not None:
            stmt = stmt.where(AlertModel.client_id == client_id)
        stmt = stmt.order_by(AlertModel.opened_at.desc(), AlertModel.id.desc()).limit(limit)
        return [to_entity(m) for m in (await self._session.execute(stmt)).scalars()]

    async def count_by_status(self, *, client_id: UUID | None = None) -> dict[AlertStatus, int]:
        """Cuántas alertas hay en cada estado, de todos los clientes o de uno."""
        stmt = select(AlertModel.status, func.count()).group_by(AlertModel.status)
        if client_id is not None:
            stmt = stmt.where(AlertModel.client_id == client_id)
        return {AlertStatus(st): int(n) for st, n in (await self._session.execute(stmt)).all()}

    async def count_open_by_severity(self) -> dict[Severity, int]:
        stmt = (
            select(AlertModel.severity, func.count())
            .where(AlertModel.status.in_([s.value for s in LIVE_STATUSES]))
            .group_by(AlertModel.severity)
        )
        return {Severity(sev): int(n) for sev, n in (await self._session.execute(stmt)).all()}


class SqlAlchemyAlertRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def overrides(self) -> dict[str, tuple[bool, float | None, Severity]]:
        rows = (await self._session.execute(select(AlertRuleModel))).scalars()
        return {r.code: (r.enabled, r.threshold, Severity(r.severity)) for r in rows}

    async def set(
        self, code: str, *, enabled: bool, threshold: float | None, severity: Severity
    ) -> None:
        model = await self._session.get(AlertRuleModel, code)
        if model is None:
            self._session.add(
                AlertRuleModel(
                    code=code, enabled=enabled, threshold=threshold, severity=severity.value
                )
            )
        else:
            model.enabled = enabled
            model.threshold = threshold
            model.severity = severity.value
        await self._session.flush()
