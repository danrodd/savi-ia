from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Index, String, Uuid, and_, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.audit.domain import AuditEntry
from app.shared.clock import as_utc

JsonType = JSON().with_variant(JSONB(), "postgresql")


class AuditLogModel(Base):
    """Solo inserción. En Postgres la migración 0003 bloquea UPDATE y DELETE con un trigger."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_occurred_at_id", "occurred_at", "id"),
        Index("ix_audit_log_actor_staff_id", "actor_staff_id"),
        Index("ix_audit_log_action", "action"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Sin FK: la auditoría sobrevive aunque el usuario del staff se elimine algún día.
    actor_staff_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)


def _to_entity(m: AuditLogModel) -> AuditEntry:
    return AuditEntry(
        id=m.id,
        occurred_at=as_utc(m.occurred_at),
        actor_staff_id=m.actor_staff_id,
        actor_email=m.actor_email,
        action=m.action,
        target_type=m.target_type,
        target_id=m.target_id,
        before=m.before,
        after=m.after,
        ip=m.ip,
        user_agent=m.user_agent,
    )


class SqlAlchemyAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: AuditEntry) -> None:
        self._session.add(
            AuditLogModel(
                id=entry.id,
                occurred_at=entry.occurred_at,
                actor_staff_id=entry.actor_staff_id,
                actor_email=entry.actor_email,
                action=entry.action,
                target_type=entry.target_type,
                target_id=entry.target_id,
                before=entry.before,
                after=entry.after,
                ip=entry.ip,
                user_agent=entry.user_agent,
            )
        )
        await self._session.flush()

    async def list(
        self,
        *,
        actor: str | None,
        action: str | None,
        target: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        before_id: tuple[datetime, UUID] | None,
    ) -> list[AuditEntry]:
        stmt = select(AuditLogModel)
        if actor:
            stmt = stmt.where(AuditLogModel.actor_email == actor.lower())
        if action:
            stmt = stmt.where(AuditLogModel.action == action)
        if target:
            stmt = stmt.where(AuditLogModel.target_id == target)
        if start:
            stmt = stmt.where(AuditLogModel.occurred_at >= start)
        if end:
            stmt = stmt.where(AuditLogModel.occurred_at < end)
        if before_id:
            at, entry_id = before_id
            stmt = stmt.where(
                or_(
                    AuditLogModel.occurred_at < at,
                    and_(AuditLogModel.occurred_at == at, AuditLogModel.id < entry_id),
                )
            )
        stmt = stmt.order_by(AuditLogModel.occurred_at.desc(), AuditLogModel.id.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [_to_entity(m) for m in result.scalars()]
