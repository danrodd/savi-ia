from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Uuid,
    or_,
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
        # La autenticación también busca por el secreto anterior (vale 24 h tras rotar).
        Index("ix_instances_previous_secret_hash", "previous_secret_hash"),
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
    rotation_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _opt(value: datetime | None) -> datetime | None:
    return as_utc(value) if value else None


def to_entity(m: InstanceModel) -> Instance:
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
        rotation_requested_at=_opt(m.rotation_requested_at),
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
                rotation_requested_at=instance.rotation_requested_at,
                created_at=instance.created_at,
                updated_at=instance.updated_at,
            )
        )
        await self._session.flush()

    async def get_by_id(self, instance_id: UUID) -> Instance | None:
        model = await self._session.get(InstanceModel, instance_id)
        return to_entity(model) if model else None

    async def get_for_update(self, instance_id: UUID) -> Instance | None:
        result = await self._session.execute(
            select(InstanceModel)
            .where(InstanceModel.id == instance_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = result.scalar_one_or_none()
        return to_entity(model) if model else None

    async def get_by_secret_hash(self, secret_hash: bytes) -> Instance | None:
        result = await self._session.execute(
            select(InstanceModel).where(
                or_(
                    InstanceModel.secret_hash == secret_hash,
                    InstanceModel.previous_secret_hash == secret_hash,
                )
            )
        )
        model = result.scalars().first()
        return to_entity(model) if model else None

    async def list_by_client(self, client_id: UUID) -> list[Instance]:
        result = await self._session.execute(
            select(InstanceModel)
            .where(InstanceModel.client_id == client_id)
            .order_by(InstanceModel.enrolled_at)
        )
        return [to_entity(m) for m in result.scalars()]

    async def save(self, instance: Instance) -> None:
        model = await self._session.get(InstanceModel, instance.id)
        if model is None:
            raise LookupError(f"Instancia {instance.id} no existe")
        model.deployment_mode = instance.deployment_mode
        model.version = instance.version
        model.commit = instance.commit
        model.status = instance.status.value
        model.status_reason = instance.status_reason
        model.secret_hash = instance.secret_hash
        model.previous_secret_hash = instance.previous_secret_hash
        model.previous_secret_expires_at = instance.previous_secret_expires_at
        model.fingerprint = instance.fingerprint
        model.last_seen_at = instance.last_seen_at
        model.last_heartbeat = instance.last_heartbeat
        model.clock_skew_seconds = instance.clock_skew_seconds
        model.rotation_requested_at = instance.rotation_requested_at
        model.updated_at = instance.updated_at
        await self._session.flush()


class HeartbeatModel(Base):
    __tablename__ = "heartbeats"
    __table_args__ = (Index("ix_heartbeats_instance_id_received_at", "instance_id", "received_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    instance_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("instances.id", ondelete="CASCADE"), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class SqlAlchemyHeartbeatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, instance_id: UUID, received_at: datetime, payload: dict[str, Any]) -> None:
        self._session.add(
            HeartbeatModel(
                id=uuid4(), instance_id=instance_id, received_at=received_at, payload=payload
            )
        )
        await self._session.flush()
