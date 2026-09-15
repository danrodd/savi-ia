from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base
from app.infrastructure.database.types import JsonType, UtcDateTime, UuidType


class ConversationModel(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(UuidType, primary_key=True, default=uuid4)
    # `idUsuario` del ERP (entero). Nullable solo por compatibilidad con
    # conversaciones legadas anteriores a auth — las nuevas siempre tienen.
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Base del ERP de esta conversacion. Se fija al crearla y NO cambia:
    # el historial es el contexto que se le manda al LLM en cada turno, y
    # si la base cambiara a mitad del hilo el modelo razonaria sobre datos
    # mezclados de dos clientes. Cambiar de cliente = conversacion nueva.
    #
    # Junto con `user_id` forma la identidad del dueno: el `idUsuario` se
    # repite entre bases y filtrar solo por el cruzaria conversaciones
    # entre clientes.
    #
    # Nullable por las conversaciones anteriores al multi-BD; las nuevas
    # siempre la tienen (lo exige la capa de aplicacion).
    erp_database_id: Mapped[UUID | None] = mapped_column(
        UuidType,
        ForeignKey("erp_databases.id"),
        nullable=True,
    )
    # Base de IDENTIDAD del dueño (con la que inició sesión), separada de
    # `erp_database_id` (la base CONSULTADA por esta conversación). Con
    # D10 un usuario puede tener conversaciones de varios clientes a la
    # vez sin haber cambiado de sesión: los filtros de dueño (listado,
    # ownership del chat, "mi consumo") tienen que comparar contra esta
    # columna, nunca contra la consultada. Ver migración d1a4c8f0e921.
    owner_erp_database_id: Mapped[UUID | None] = mapped_column(
        UuidType,
        ForeignKey("erp_databases.id"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    title_locked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime,
        nullable=True,
    )

    messages: Mapped[list["MessageModel"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="MessageModel.created_at",
    )

    __table_args__ = (
        # Ranking de consumo por cliente (`usage.per_user`): agrupa por la
        # base CONSULTADA, no por la de identidad.
        Index("ix_conversations_user_id", "erp_database_id", "user_id"),
        # Filtrado por dueño: listado, ownership del chat, "mi consumo".
        Index("ix_conversations_owner", "owner_erp_database_id", "user_id"),
        Index("ix_conversations_updated_at", "updated_at"),
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(UuidType, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        UuidType,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    finish_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tool_invocations: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JsonType,
        nullable=True,
    )
    usage: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Documentos de la empresa citados (`MessageSource.to_dict`). NULL = sin citas.
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonType, nullable=True)
    # Revisiones: cuando un mensaje se edita o se regenera, el viejo NO se
    # borra: queda con `superseded_at=now()` y `superseded_by_id` apuntando
    # al mensaje que lo reemplazó. El hilo activo se filtra por
    # `superseded_at IS NULL`.
    superseded_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime,
        nullable=True,
    )
    superseded_by_id: Mapped[UUID | None] = mapped_column(
        UuidType,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped[ConversationModel] = relationship(back_populates="messages")

    __table_args__ = (
        # Optimizado para "hilo activo de la conversación" (la query default).
        Index(
            "ix_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),
        # Optimizado para reconstruir versiones de un mensaje superseded.
        Index(
            "ix_messages_superseded_by",
            "superseded_by_id",
        ),
    )
