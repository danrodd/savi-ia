"""Impl `RefreshTokenRepository` con sessionmaker independiente.

Igual que los writers del módulo `chat`: cada operación abre su propia
sesión. Esto evita acoplar el lifecycle del refresh al request del chat
y permite revocaciones que sobreviven a cancelaciones.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.domain.entities import RefreshTokenRecord
from app.modules.auth.domain.interfaces import RefreshTokenRepository
from app.modules.auth.infrastructure.persistence.models import RefreshTokenModel


class SqlAlchemyRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def save(self, record: RefreshTokenRecord) -> None:
        async with self._sessionmaker() as session:
            session.add(
                RefreshTokenModel(
                    jti=record.jti,
                    user_id=record.user_id,
                    user_login=record.user_login,
                    expires_at=record.expires_at,
                    revoked_at=record.revoked_at,
                )
            )
            await session.commit()

    async def get_by_jti(self, jti: UUID) -> RefreshTokenRecord | None:
        async with self._sessionmaker() as session:
            stmt = select(RefreshTokenModel).where(RefreshTokenModel.jti == jti)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return RefreshTokenRecord(
                jti=row.jti,
                user_id=row.user_id,
                user_login=row.user_login,
                expires_at=row.expires_at,
                created_at=row.created_at,
                revoked_at=row.revoked_at,
            )

    async def revoke(self, jti: UUID, *, when: datetime) -> bool:
        async with self._sessionmaker() as session:
            stmt = (
                update(RefreshTokenModel)
                .where(
                    RefreshTokenModel.jti == jti,
                    RefreshTokenModel.revoked_at.is_(None),
                )
                .values(revoked_at=when)
                .returning(RefreshTokenModel.jti)
            )
            result = await session.execute(stmt)
            ok = result.scalar_one_or_none() is not None
            await session.commit()
            return ok

    async def revoke_all_for_user(self, user_id: int, *, when: datetime) -> None:
        async with self._sessionmaker() as session:
            stmt = (
                update(RefreshTokenModel)
                .where(
                    RefreshTokenModel.user_id == user_id,
                    RefreshTokenModel.revoked_at.is_(None),
                )
                .values(revoked_at=when)
            )
            await session.execute(stmt)
            await session.commit()
