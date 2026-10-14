from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, String, Uuid, select
from sqlalchemy import false as sa_false
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.clients.domain import (
    Client,
    ClientCodeAlreadyExists,
    ClientStatus,
    IdentityMode,
)
from app.modules.clients.policies import AccessPolicy, AiPolicy
from app.shared.clock import as_utc


class ClientModel(Base):
    __tablename__ = "clients"
    __table_args__ = (
        CheckConstraint("status in ('active', 'suspended')", name="status_valid"),
        CheckConstraint("length(code) between 2 and 32", name="code_length"),
        CheckConstraint("identity_mode in ('pseudonym', 'named')", name="identity_mode_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    nit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    identity_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pseudonym", server_default="pseudonym"
    )
    config_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false()
    )
    allow_local_cli: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false()
    )
    ai_policy: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    access_policy: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


def to_entity(model: ClientModel) -> Client:
    return Client(
        id=model.id,
        code=model.code,
        name=model.name,
        nit=model.nit,
        status=ClientStatus(model.status),
        created_at=as_utc(model.created_at),
        updated_at=as_utc(model.updated_at),
        identity_mode=IdentityMode(model.identity_mode),
        config_locked=model.config_locked,
        allow_local_cli=model.allow_local_cli,
        ai_policy=AiPolicy.from_json(model.ai_policy),
        access_policy=AccessPolicy.from_json(model.access_policy),
    )


class SqlAlchemyClientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, client: Client) -> None:
        model = ClientModel(
            id=client.id,
            code=client.code,
            name=client.name,
            nit=client.nit,
            status=client.status.value,
            created_at=client.created_at,
            updated_at=client.updated_at,
            identity_mode=client.identity_mode.value,
            config_locked=client.config_locked,
            allow_local_cli=client.allow_local_cli,
            ai_policy=client.ai_policy.to_json() if not client.ai_policy.is_empty else None,
            access_policy=(
                client.access_policy.to_json() if not client.access_policy.is_empty else None
            ),
        )
        try:
            async with self._session.begin_nested():
                self._session.add(model)
        except IntegrityError as exc:
            raise ClientCodeAlreadyExists(
                f"Ya existe un cliente con el código {client.code}."
            ) from exc

    async def get_by_id(self, client_id: UUID) -> Client | None:
        model = await self._session.get(ClientModel, client_id)
        return to_entity(model) if model else None

    async def get_by_code(self, code: str) -> Client | None:
        result = await self._session.execute(select(ClientModel).where(ClientModel.code == code))
        model = result.scalar_one_or_none()
        return to_entity(model) if model else None

    async def save(self, client: Client) -> None:
        model = await self._session.get(ClientModel, client.id)
        if model is None:
            raise LookupError(f"Cliente {client.id} no existe")
        model.name = client.name
        model.nit = client.nit
        model.status = client.status.value
        model.identity_mode = client.identity_mode.value
        model.config_locked = client.config_locked
        model.allow_local_cli = client.allow_local_cli
        model.ai_policy = client.ai_policy.to_json() if not client.ai_policy.is_empty else None
        model.access_policy = (
            client.access_policy.to_json() if not client.access_policy.is_empty else None
        )
        model.updated_at = client.updated_at
        await self._session.flush()

    async def list_all(self) -> list[Client]:
        result = await self._session.execute(select(ClientModel).order_by(ClientModel.code))
        return [to_entity(m) for m in result.scalars()]
