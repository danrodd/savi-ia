"""Impl `TotpRepository` con sessionmaker independiente (mismo patrón que los refresh)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.domain.entities import UserTotp
from app.modules.auth.domain.interfaces import TotpRepository
from app.modules.auth.infrastructure.persistence.models import UserTotpModel
from app.shared.security import CredentialCipher, CredentialDecryptError


class SqlAlchemyTotpRepository(TotpRepository):
    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], cipher: CredentialCipher
    ) -> None:
        self._sessionmaker = sessionmaker
        self._cipher = cipher

    async def get(self, *, erp_database_id: UUID, user_id: int) -> UserTotp | None:
        async with self._sessionmaker() as session:
            row = await session.get(UserTotpModel, (erp_database_id, user_id))
            if row is None:
                return None
            secret: str | None
            unreadable = False
            try:
                secret = self._cipher.decrypt(row.secret_encrypted)
            except CredentialDecryptError:
                # La clave del servidor cambió: no se puede verificar ni reemplazar en silencio.
                secret, unreadable = None, True
            return UserTotp(
                erp_database_id=row.erp_database_id,
                user_id=row.user_id,
                user_login=row.user_login,
                secret=secret,
                enabled_at=row.enabled_at,
                last_step=row.last_step,
                unreadable=unreadable,
            )

    async def save_pending(
        self,
        *,
        erp_database_id: UUID,
        user_id: int,
        user_login: str,
        secret: str,
        when: datetime,
    ) -> None:
        async with self._sessionmaker() as session:
            row = await session.get(UserTotpModel, (erp_database_id, user_id))
            if row is None:
                session.add(
                    UserTotpModel(
                        erp_database_id=erp_database_id,
                        user_id=user_id,
                        user_login=user_login,
                        secret_encrypted=self._cipher.encrypt(secret),
                        enabled_at=None,
                        last_step=0,
                        created_at=when,
                    )
                )
            elif row.enabled_at is None:
                row.secret_encrypted = self._cipher.encrypt(secret)
                row.user_login = user_login
                row.last_step = 0
            else:
                # Defensa en profundidad: el servicio ya lo impide.
                raise ValueError("El usuario ya tiene un segundo factor activo.")
            await session.commit()

    async def enable(
        self, *, erp_database_id: UUID, user_id: int, last_step: int, when: datetime
    ) -> bool:
        async with self._sessionmaker() as session:
            result = await session.execute(
                update(UserTotpModel)
                .where(
                    UserTotpModel.erp_database_id == erp_database_id,
                    UserTotpModel.user_id == user_id,
                    UserTotpModel.enabled_at.is_(None),
                )
                .values(enabled_at=when, last_step=last_step)
            )
            await session.commit()
            return bool(getattr(result, "rowcount", 0))

    async def advance_step(self, *, erp_database_id: UUID, user_id: int, step: int) -> bool:
        async with self._sessionmaker() as session:
            # Condicional en SQL: dos pedidos con el mismo código compiten por esta fila y solo
            # uno la actualiza.
            result = await session.execute(
                update(UserTotpModel)
                .where(
                    UserTotpModel.erp_database_id == erp_database_id,
                    UserTotpModel.user_id == user_id,
                    UserTotpModel.enabled_at.is_not(None),
                    UserTotpModel.last_step < step,
                )
                .values(last_step=step)
            )
            await session.commit()
            return bool(getattr(result, "rowcount", 0))

    async def delete_by_login(self, *, erp_database_id: UUID, user_login: str) -> int | None:
        async with self._sessionmaker() as session:
            found = await session.execute(
                select(UserTotpModel.user_id).where(
                    UserTotpModel.erp_database_id == erp_database_id,
                    UserTotpModel.user_login == user_login,
                )
            )
            user_id = found.scalar_one_or_none()
            if user_id is None:
                return None
            await session.execute(
                delete(UserTotpModel).where(
                    UserTotpModel.erp_database_id == erp_database_id,
                    UserTotpModel.user_id == user_id,
                )
            )
            await session.commit()
            return int(user_id)
