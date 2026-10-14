from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Uuid,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.instances.domain import Instance, InstanceStatus
from app.shared.clock import as_utc

JsonType = JSON().with_variant(JSONB(), "postgresql")


class InstanceModel(Base):
    __tablename__ = "instances"
    __table_args__ = (
        CheckConstraint("status in ('active', 'suspended', 'revoked')", name="status_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    client_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    deployment_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    os: Mapped[str] = mapped_column(String(200), nullable=False)
    agent_db_engine: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    status_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    secret_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    previous_secret_hash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    previous_secret_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    clock_skew_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _opt(value: datetime | None) -> datetime | None:
    return as_utc(value) if value else None


def _to_entity(m: InstanceModel) -> Instance:
    return Instance(
        id=m.id,
        client_id=m.client_id,
        name=m.name,
        deployment_mode=m.deployment_mode,
        os=m.os,
        agent_db_engine=m.agent_db_engine,
        version=m.version,
        commit=m.commit,
        status=InstanceStatus(m.status),
        status_reason=m.status_reason,
        secret_hash=bytes(m.secret_hash),
        previous_secret_hash=bytes(m.previous_secret_hash) if m.previous_secret_hash else None,
        previous_secret_expires_at=_opt(m.previous_secret_expires_at),
        fingerprint=m.fingerprint,
        enrolled_at=as_utc(m.enrolled_at),
        last_seen_at=_opt(m.last_seen_at),
        last_heartbeat=m.last_heartbeat,
        clock_skew_seconds=m.clock_skew_seconds,
        created_at=as_utc(m.created_at),
        updated_at=as_utc(m.updated_at),
    )


class SqlAlchemyInstanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, instance: Instance) -> None:
        self._session.add(
            InstanceModel(
                id=instance.id,
                client_id=instance.client_id,
                name=instance.name,
                deployment_mode=instance.deployment_mode,
                os=instance.os,
                agent_db_engine=instance.agent_db_engine,
                version=instance.version,
                commit=instance.commit,
                status=instance.status.value,
                status_reason=instance.status_reason,
                secret_hash=instance.secret_hash,
                previous_secret_hash=instance.previous_secret_hash,
                previous_secret_expires_at=instance.previous_secret_expires_at,
                fingerprint=instance.fingerprint,
                enrolled_at=instance.enrolled_at,
                last_seen_at=instance.last_seen_at,
                last_heartbeat=instance.last_heartbeat,
                clock_skew_seconds=instance.clock_skew_seconds,
                created_at=instance.created_at,
                updated_at=instance.updated_at,
            )
        )
        await self._session.flush()

    async def list_by_client(self, client_id: UUID) -> list[Instance]:
        result = await self._session.execute(
            select(InstanceModel)
            .where(InstanceModel.client_id == client_id)
            .order_by(InstanceModel.enrolled_at)
        )
        return [_to_entity(m) for m in result.scalars()]
