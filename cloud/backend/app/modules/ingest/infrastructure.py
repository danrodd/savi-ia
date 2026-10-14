"""Persistencia de eventos: una tabla tipada por stream (§7.2).

Pendiente para E4: particionado por mes (retención de 13 meses en eventos, 7 días en
`ingest_batches`, 30 días en `heartbeats`). Particionar exige que la clave de partición
(`occurred_at`) forme parte de las PK; hay que resolver cómo conservar la idempotencia por
`(instance_id, source_id)` antes de hacerlo. Por ahora las tablas son planas y las PK de
idempotencia están completas.

Las tablas de eventos no llevan FK a `instances`/`clients`: el volumen es alto y la integridad
la garantiza la autenticación (solo se escribe con una instancia válida).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Uuid,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.ingest.domain import IngestOutcome
from app.shared.sync_v1 import (
    AnyEvent,
    ConversationEvent,
    FreeQueryEvent,
    RejectedEvent,
    SessionEvent,
    TurnEvent,
)

JsonType = JSON().with_variant(JSONB(), "postgresql")


class IngestBatchModel(Base):
    __tablename__ = "ingest_batches"

    instance_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("instances.id", ondelete="CASCADE"), primary_key=True
    )
    batch_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected: Mapped[list[dict[str, str]]] = mapped_column(JsonType, nullable=False)


class EvTurnModel(Base):
    __tablename__ = "ev_turns"
    __table_args__ = (Index("ix_ev_turns_client_id_occurred_at", "client_id", "occurred_at"),)

    instance_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    client_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conversation_ref: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    database_ref: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    user_ref: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_read_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_creation_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    tools: Mapped[list[dict[str, str]]] = mapped_column(JsonType, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str | None] = mapped_column(String(16), nullable=True)


class EvConversationModel(Base):
    __tablename__ = "ev_conversations"
    __table_args__ = (
        Index("ix_ev_conversations_client_id_occurred_at", "client_id", "occurred_at"),
    )

    instance_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    client_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conversation_ref: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    database_ref: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    user_ref: Mapped[str] = mapped_column(String(32), nullable=False)


class EvSessionModel(Base):
    __tablename__ = "ev_sessions"
    __table_args__ = (Index("ix_ev_sessions_client_id_occurred_at", "client_id", "occurred_at"),)

    instance_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    client_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_ref: Mapped[str] = mapped_column(String(32), nullable=False)
    database_ref: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # Solo clientes en modo `named` (la organización interna). Nulo para el resto.
    user_label: Mapped[str | None] = mapped_column(String(64), nullable=True)


class EvFreeQueryModel(Base):
    __tablename__ = "ev_free_queries"
    __table_args__ = (
        Index("ix_ev_free_queries_client_id_occurred_at", "client_id", "occurred_at"),
    )

    instance_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    client_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conversation_ref: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    database_ref: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    estimated_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    returned_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class InstanceDatabaseModel(Base):
    """Snapshot diario del inventario de bases: una fila por base y día."""

    __tablename__ = "instance_databases"
    __table_args__ = (
        Index("ix_instance_databases_client_id_occurred_at", "client_id", "occurred_at"),
    )

    instance_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    database_ref: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    client_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_usable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    credentials_unreadable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    last_connection_ok_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


@dataclass(frozen=True)
class _Target:
    """Tabla destino de un grupo de eventos y las columnas de su clave de idempotencia."""

    model: type[Base]
    key: tuple[str, ...]


_TURNS = _Target(EvTurnModel, ("instance_id", "source_id"))
_CONVERSATIONS = _Target(EvConversationModel, ("instance_id", "source_id"))
_SESSIONS = _Target(EvSessionModel, ("instance_id", "source_id"))
_FREE_QUERIES = _Target(EvFreeQueryModel, ("instance_id", "source_id"))
_DATABASES = _Target(InstanceDatabaseModel, ("instance_id", "database_ref", "snapshot_date"))


def _uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


def _row(event: AnyEvent, instance_id: UUID, client_id: UUID) -> tuple[_Target, dict[str, Any]]:
    occurred = event.occurred_at.astimezone(UTC)
    base: dict[str, Any] = {
        "instance_id": instance_id,
        "client_id": client_id,
        "occurred_at": occurred,
    }
    if isinstance(event, TurnEvent):
        d = event.data
        return _TURNS, {
            **base,
            "source_id": event.source_id,
            "conversation_ref": UUID(d.conversation_ref),
            "database_ref": _uuid(d.database_ref),
            "user_ref": d.user_ref,
            "provider": d.provider,
            "model": d.model,
            "finish_reason": d.finish_reason,
            "input_tokens": d.input_tokens,
            "output_tokens": d.output_tokens,
            "cache_read_input_tokens": d.cache_read_input_tokens,
            "cache_creation_input_tokens": d.cache_creation_input_tokens,
            "cost_usd": Decimal(d.cost_usd) if d.cost_usd is not None else None,
            "tools": [t.model_dump(exclude_none=True) for t in d.tools],
            "latency_ms": d.latency_ms,
            "action": d.action,
        }
    if isinstance(event, ConversationEvent):
        c = event.data
        return _CONVERSATIONS, {
            **base,
            "source_id": event.source_id,
            "conversation_ref": UUID(c.conversation_ref),
            "database_ref": _uuid(c.database_ref),
            "user_ref": c.user_ref,
        }
    if isinstance(event, SessionEvent):
        s = event.data
        return _SESSIONS, {
            **base,
            "source_id": event.source_id,
            "user_ref": s.user_ref,
            "user_label": s.user_label,
            "database_ref": _uuid(s.database_ref),
        }
    if isinstance(event, FreeQueryEvent):
        f = event.data
        return _FREE_QUERIES, {
            **base,
            "source_id": event.source_id,
            "conversation_ref": _uuid(f.conversation_ref),
            "database_ref": _uuid(f.database_ref),
            "result": f.result,
            "estimated_rows": f.estimated_rows,
            "returned_rows": f.returned_rows,
            "duration_ms": f.duration_ms,
        }
    b = event.data
    return _DATABASES, {
        **base,
        "database_ref": UUID(b.database_ref),
        "snapshot_date": occurred.date(),
        "code": b.code,
        "name": b.name,
        "is_active": b.is_active,
        "is_usable": b.is_usable,
        "credentials_unreadable": b.credentials_unreadable,
        "last_connection_ok_at": b.last_connection_ok_at,
    }


class SqlAlchemyIngestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _insert_ignoring_conflicts(
        self, model: type[Base], rows: list[dict[str, Any]], key: Sequence[str]
    ) -> Any:
        # Producción es Postgres; SQLite solo existe para los tests rápidos. Ambos dialectos
        # entienden `ON CONFLICT DO NOTHING` con la misma forma.
        insert = (
            pg_insert if self._session.get_bind().dialect.name == "postgresql" else sqlite_insert
        )
        return insert(model).values(rows).on_conflict_do_nothing(index_elements=list(key))

    async def claim_batch(
        self, instance_id: UUID, batch_id: UUID, received_at: datetime
    ) -> IngestOutcome | None:
        statement = self._insert_ignoring_conflicts(
            IngestBatchModel,
            [
                {
                    "instance_id": instance_id,
                    "batch_id": batch_id,
                    "received_at": received_at,
                    "accepted": 0,
                    "duplicates": 0,
                    "rejected": [],
                }
            ],
            ("instance_id", "batch_id"),
        )
        # Si otro request con el mismo lote está en curso, el INSERT espera a que confirme.
        result = await self._session.execute(statement)
        if result.rowcount == 1:  # type: ignore[attr-defined]
            return None
        stored = await self._session.execute(
            select(IngestBatchModel).where(
                IngestBatchModel.instance_id == instance_id,
                IngestBatchModel.batch_id == batch_id,
            )
        )
        model = stored.scalar_one()
        return IngestOutcome(
            accepted=model.accepted,
            duplicates=model.duplicates,
            rejected=[
                RejectedEvent.model_validate(r)  # reason/source_id los escribimos nosotros
                for r in model.rejected
            ],
        )

    async def insert_events(
        self, instance_id: UUID, client_id: UUID, events: Sequence[AnyEvent]
    ) -> int:
        groups: dict[type[Base], tuple[_Target, list[dict[str, Any]]]] = {}
        for event in events:
            target, row = _row(event, instance_id, client_id)
            groups.setdefault(target.model, (target, []))[1].append(row)
        inserted = 0
        for target, rows in groups.values():
            result = await self._session.execute(
                self._insert_ignoring_conflicts(target.model, rows, target.key)
            )
            inserted += int(result.rowcount)  # type: ignore[attr-defined]
        return inserted

    async def complete_batch(
        self, instance_id: UUID, batch_id: UUID, outcome: IngestOutcome
    ) -> None:
        await self._session.execute(
            update(IngestBatchModel)
            .where(
                IngestBatchModel.instance_id == instance_id,
                IngestBatchModel.batch_id == batch_id,
            )
            .values(
                accepted=outcome.accepted,
                duplicates=outcome.duplicates,
                rejected=[r.model_dump() for r in outcome.rejected],
            )
        )
