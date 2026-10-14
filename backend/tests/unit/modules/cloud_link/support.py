"""Piezas compartidas de los tests de `cloud_link`: una `CloudApi` falsa con
fallos programables, un reloj controlable y sembradores de filas."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.infrastructure.persistence.models import RefreshTokenModel
from app.modules.cloud_link.domain.entities import CloudNotice
from app.modules.cloud_link.domain.exceptions import CloudApiError
from app.modules.cloud_link.domain.interfaces import (
    CloudApi,
    EnrollResult,
    HeartbeatResult,
    IngestResult,
    JsonObject,
    RejectedEvent,
)
from app.modules.cloud_link.domain.value_objects import SyncPolicy
from app.modules.conversations.infrastructure.persistence.models import (
    ConversationModel,
    MessageModel,
)
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel
from app.modules.free_query.infrastructure.models import AuditQueryModel

DB_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
DB_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
T0 = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
SECRET = "svk_ins_" + "A" * 43
NEW_SECRET = "svk_ins_" + "B" * 43
CLOUD_URL = "https://cloud.example.test"


class FakeClock:
    def __init__(self, start: datetime = T0) -> None:
        self.current = start

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


@dataclass
class IngestCall:
    batch_id: str
    events: list[JsonObject]
    secret: str


@dataclass
class FakeCloudApi(CloudApi):
    """`CloudApi` en memoria. `ingest_errors[n]` hace fallar el n-ésimo
    `ingest` (1-based) con ese error."""

    policy: SyncPolicy = field(default_factory=SyncPolicy)
    instance_status: str = "active"
    notices: list[CloudNotice] = field(default_factory=list[CloudNotice])
    enroll_error: CloudApiError | None = None
    heartbeat_error: CloudApiError | None = None
    rotate_error: CloudApiError | None = None
    ingest_errors: dict[int, CloudApiError] = field(default_factory=dict[int, CloudApiError])
    # Con la instancia suspendida Cloud responde 200 y `accepted = 0`.
    store_nothing: bool = False
    # Si se define, reemplaza el comportamiento de `ingest` (p. ej. colgarse).
    ingest_hook: Callable[[IngestCall], Awaitable[None]] | None = None
    heartbeat_hook: Callable[[], Awaitable[None]] | None = None
    enroll_calls: list[tuple[str, JsonObject]] = field(default_factory=list[tuple[str, JsonObject]])
    heartbeats: list[JsonObject] = field(default_factory=list[JsonObject])
    ingests: list[IngestCall] = field(default_factory=list[IngestCall])
    rotations: int = 0
    seen_ids: set[str] = field(default_factory=set[str])
    attempts: int = 0

    async def enroll(self, *, cloud_url: str, token: str, instance: JsonObject) -> EnrollResult:
        self.enroll_calls.append((token, instance))
        if self.enroll_error is not None:
            raise self.enroll_error
        return EnrollResult(
            instance_id=uuid4(),
            instance_secret=SECRET,
            client_code="FARMX",
            client_name="Farmacias X",
            policy=self.policy,
        )

    async def heartbeat(
        self, *, cloud_url: str, secret: str, payload: JsonObject
    ) -> HeartbeatResult:
        if self.heartbeat_hook is not None:
            await self.heartbeat_hook()
        if self.heartbeat_error is not None:
            raise self.heartbeat_error
        self.heartbeats.append(payload)
        return HeartbeatResult(
            instance_status=self.instance_status, policy=self.policy, notices=list(self.notices)
        )

    async def ingest(
        self,
        *,
        cloud_url: str,
        secret: str,
        batch_id: str,
        sent_at: datetime,
        events: Sequence[JsonObject],
    ) -> IngestResult:
        self.attempts += 1
        call = IngestCall(batch_id=batch_id, events=list(events), secret=secret)
        self.ingests.append(call)
        if self.ingest_hook is not None:
            await self.ingest_hook(call)
        error = self.ingest_errors.get(self.attempts)
        if error is not None:
            raise error
        if self.store_nothing:
            return IngestResult(accepted=0, duplicates=0, rejected=[])
        accepted = duplicates = 0
        rejected: list[RejectedEvent] = []
        for event in events:
            key = f"{event['schema']}:{event['source_id']}"
            if key in self.seen_ids:
                duplicates += 1
            else:
                self.seen_ids.add(key)
                accepted += 1
        return IngestResult(accepted=accepted, duplicates=duplicates, rejected=rejected)

    async def rotate(self, *, cloud_url: str, secret: str) -> str:
        if self.rotate_error is not None:
            raise self.rotate_error
        self.rotations += 1
        return NEW_SECRET

    # ── lecturas cómodas ─────────────────────────────────────────────────

    def events(self, schema: str) -> list[JsonObject]:
        return [e for call in self.ingests for e in call.events if e["schema"] == schema]

    def unique_source_ids(self, schema: str) -> list[str]:
        return list(dict.fromkeys(str(e["source_id"]) for e in self.events(schema)))


def net_error() -> CloudApiError:
    return CloudApiError("network_error")


def http_error(status: int, code: str, *, retry_after: float | None = None) -> CloudApiError:
    return CloudApiError(code, status_code=status, retry_after_seconds=retry_after)


async def seed_erp_databases(sm: async_sessionmaker[AsyncSession]) -> None:
    async with sm() as session:
        for database_id, code, name in ((DB_A, "NORTE", "Sede Norte"), (DB_B, "SUR", "Sede Sur")):
            session.add(
                ErpDatabaseModel(
                    id=database_id,
                    code=code,
                    name=name,
                    host=f"srv-{code.lower()}.interno.local",
                    port=5432,
                    database=f"erp_{code.lower()}_fisica",
                    username="usuario_secreto",
                    password_encrypted="cifrado",
                )
            )
        await session.commit()


async def add_conversation(
    sm: async_sessionmaker[AsyncSession],
    *,
    user_id: int = 7,
    owner: UUID = DB_A,
    queried: UUID = DB_A,
    created_at: datetime = T0,
    title: str = "Título con datos sensibles",
    conversation_id: UUID | None = None,
) -> UUID:
    cid = conversation_id or uuid4()
    async with sm() as session:
        session.add(
            ConversationModel(
                id=cid,
                user_id=user_id,
                erp_database_id=queried,
                owner_erp_database_id=owner,
                title=title,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await session.commit()
    return cid


async def add_message(
    sm: async_sessionmaker[AsyncSession],
    conversation_id: UUID,
    *,
    role: str = "assistant",
    created_at: datetime = T0,
    content: str = "Contenido que nunca debe viajar",
    usage: dict[str, Any] | None = None,
    cost: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    provider: str | None = "claude",
    model: str | None = "claude-sonnet-4-6",
    finish_reason: str | None = "complete",
    message_id: UUID | None = None,
    superseded_by_id: UUID | None = None,
) -> UUID:
    mid = message_id or uuid4()
    async with sm() as session:
        session.add(
            MessageModel(
                id=mid,
                conversation_id=conversation_id,
                role=role,
                content=content,
                created_at=created_at,
                usage=usage,
                cost_usd=Decimal(cost) if cost is not None else None,
                tool_invocations=tools,
                provider=provider if role == "assistant" else None,
                model=model if role == "assistant" else None,
                finish_reason=finish_reason if role == "assistant" else None,
                superseded_at=T0 if superseded_by_id is not None else None,
                superseded_by_id=superseded_by_id,
            )
        )
        await session.commit()
    return mid


async def add_session_token(
    sm: async_sessionmaker[AsyncSession],
    *,
    user_id: int = 7,
    database: UUID = DB_A,
    created_at: datetime = T0,
) -> UUID:
    jti = uuid4()
    async with sm() as session:
        session.add(
            RefreshTokenModel(
                jti=jti,
                user_id=user_id,
                erp_database_id=database,
                user_login="USUARIO.REAL",
                expires_at=created_at + timedelta(days=7),
                created_at=created_at,
            )
        )
        await session.commit()
    return jti


async def add_free_query(
    sm: async_sessionmaker[AsyncSession],
    *,
    conversation_id: UUID | None = None,
    database: UUID = DB_A,
    created_at: datetime = T0,
    result: str = "ok",
) -> UUID:
    qid = uuid4()
    async with sm() as session:
        session.add(
            AuditQueryModel(
                id=qid,
                conversation_id=conversation_id,
                erp_database_id=database,
                user_question="¿Cuánto debe el cliente Juan Pérez?",
                sql="SELECT * FROM clientes WHERE nombre = 'Juan Pérez'",
                result=result,
                estimated_rows=10,
                returned_rows=3,
                duration_ms=42,
                error_message='relación "secreta" no existe',
                created_at=created_at,
            )
        )
        await session.commit()
    return qid


async def hang_forever(_: Any = None) -> None:
    await asyncio.Event().wait()
