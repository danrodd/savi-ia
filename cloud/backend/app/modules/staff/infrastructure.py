from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.staff.domain import Role, StaffEmailAlreadyExists, StaffSession, StaffUser
from app.shared.clock import as_utc


class StaffUserModel(Base):
    __tablename__ = "staff_users"
    __table_args__ = (
        CheckConstraint("role in ('admin', 'soporte', 'comercial')", name="role_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    totp_last_step: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StaffSessionModel(Base):
    __tablename__ = "staff_sessions"
    __table_args__ = (Index("ix_staff_sessions_staff_user_id", "staff_user_id"),)

    jti: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    staff_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)


def _opt(value: datetime | None) -> datetime | None:
    return as_utc(value) if value else None


def _user(m: StaffUserModel) -> StaffUser:
    return StaffUser(
        id=m.id,
        email=m.email,
        full_name=m.full_name,
        password_hash=m.password_hash,
        role=Role(m.role),
        is_active=m.is_active,
        must_change_password=m.must_change_password,
        failed_attempts=m.failed_attempts,
        created_at=as_utc(m.created_at),
        updated_at=as_utc(m.updated_at),
        totp_secret_encrypted=m.totp_secret_encrypted,
        totp_enabled_at=_opt(m.totp_enabled_at),
        totp_last_step=m.totp_last_step,
        locked_until=_opt(m.locked_until),
        last_login_at=_opt(m.last_login_at),
    )


class SqlAlchemyStaffRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: StaffUser) -> None:
        model = StaffUserModel(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            password_hash=user.password_hash,
            role=user.role.value,
            totp_secret_encrypted=user.totp_secret_encrypted,
            totp_enabled_at=user.totp_enabled_at,
            totp_last_step=user.totp_last_step,
            must_change_password=user.must_change_password,
            is_active=user.is_active,
            failed_attempts=user.failed_attempts,
            locked_until=user.locked_until,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(model)
        except IntegrityError as exc:
            raise StaffEmailAlreadyExists(
                f"Ya existe un usuario con el correo {user.email}."
            ) from exc

    async def get_by_id(self, user_id: UUID) -> StaffUser | None:
        model = await self._session.get(StaffUserModel, user_id)
        return _user(model) if model else None

    async def get_by_email(self, email: str) -> StaffUser | None:
        result = await self._session.execute(
            select(StaffUserModel).where(StaffUserModel.email == email)
        )
        model = result.scalar_one_or_none()
        return _user(model) if model else None

    async def list_all(self) -> list[StaffUser]:
        result = await self._session.execute(select(StaffUserModel).order_by(StaffUserModel.email))
        return [_user(m) for m in result.scalars()]

    async def save(self, user: StaffUser) -> None:
        model = await self._session.get(StaffUserModel, user.id)
        if model is None:
            raise LookupError(f"Staff {user.id} no existe")
        model.full_name = user.full_name
        model.password_hash = user.password_hash
        model.role = user.role.value
        model.totp_secret_encrypted = user.totp_secret_encrypted
        model.totp_enabled_at = user.totp_enabled_at
        model.totp_last_step = user.totp_last_step
        model.must_change_password = user.must_change_password
        model.is_active = user.is_active
        model.failed_attempts = user.failed_attempts
        model.locked_until = user.locked_until
        model.last_login_at = user.last_login_at
        model.updated_at = user.updated_at
        await self._session.flush()

    async def count_active_admins(self) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(StaffUserModel)
            .where(StaffUserModel.role == Role.ADMIN.value, StaffUserModel.is_active.is_(True))
        )
        return int(result.scalar_one())


class SqlAlchemySessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: StaffSession) -> None:
        self._session.add(
            StaffSessionModel(
                jti=session.jti,
                staff_user_id=session.staff_user_id,
                created_at=session.created_at,
                last_used_at=session.last_used_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
                ip=session.ip,
                user_agent=session.user_agent,
            )
        )
        await self._session.flush()

    async def get(self, jti: UUID) -> StaffSession | None:
        model = await self._session.get(StaffSessionModel, jti)
        if model is None:
            return None
        return StaffSession(
            jti=model.jti,
            staff_user_id=model.staff_user_id,
            created_at=as_utc(model.created_at),
            last_used_at=as_utc(model.last_used_at),
            expires_at=as_utc(model.expires_at),
            revoked_at=_opt(model.revoked_at),
            ip=model.ip,
            user_agent=model.user_agent,
        )

    async def revoke(self, jti: UUID, at: datetime) -> None:
        await self._session.execute(
            update(StaffSessionModel)
            .where(StaffSessionModel.jti == jti, StaffSessionModel.revoked_at.is_(None))
            .values(revoked_at=at)
        )

    async def revoke_all_of_user(self, user_id: UUID, at: datetime) -> int:
        result = await self._session.execute(
            update(StaffSessionModel)
            .where(
                StaffSessionModel.staff_user_id == user_id, StaffSessionModel.revoked_at.is_(None)
            )
            .values(revoked_at=at)
        )
        return int(getattr(result, "rowcount", 0) or 0)
