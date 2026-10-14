from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.enrollments.domain import EnrollmentToken
from app.shared.clock import as_utc


class EnrollmentTokenModel(Base):
    __tablename__ = "enrollment_tokens"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    client_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # SHA-256 del token (32 bytes). El texto plano no se guarda en ningún lado.
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_instance_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("instances.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _opt(value: datetime | None) -> datetime | None:
    return as_utc(value) if value else None


def _to_entity(m: EnrollmentTokenModel) -> EnrollmentToken:
    return EnrollmentToken(
        id=m.id,
        client_id=m.client_id,
        token_hash=bytes(m.token_hash),
        expires_at=as_utc(m.expires_at),
        used_at=_opt(m.used_at),
        used_by_instance_id=m.used_by_instance_id,
        revoked_at=_opt(m.revoked_at),
        created_by=m.created_by,
        created_at=as_utc(m.created_at),
    )


class SqlAlchemyEnrollmentTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: EnrollmentToken) -> None:
        self._session.add(
            EnrollmentTokenModel(
                id=token.id,
                client_id=token.client_id,
                token_hash=token.token_hash,
                expires_at=token.expires_at,
                used_at=token.used_at,
                used_by_instance_id=token.used_by_instance_id,
                revoked_at=token.revoked_at,
                created_by=token.created_by,
                created_at=token.created_at,
            )
        )
        await self._session.flush()

    async def get_by_id(self, token_id: UUID) -> EnrollmentToken | None:
        model = await self._session.get(EnrollmentTokenModel, token_id)
        return _to_entity(model) if model else None

    async def get_by_hash_for_update(self, token_hash: bytes) -> EnrollmentToken | None:
        result = await self._session.execute(
            select(EnrollmentTokenModel)
            .where(EnrollmentTokenModel.token_hash == token_hash)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def list_by_client(self, client_id: UUID) -> list[EnrollmentToken]:
        result = await self._session.execute(
            select(EnrollmentTokenModel)
            .where(EnrollmentTokenModel.client_id == client_id)
            .order_by(EnrollmentTokenModel.created_at.desc())
        )
        return [_to_entity(m) for m in result.scalars()]

    async def save(self, token: EnrollmentToken) -> None:
        model = await self._session.get(EnrollmentTokenModel, token.id)
        if model is None:
            raise LookupError(f"Token {token.id} no existe")
        model.used_at = token.used_at
        model.used_by_instance_id = token.used_by_instance_id
        model.revoked_at = token.revoked_at
        await self._session.flush()
