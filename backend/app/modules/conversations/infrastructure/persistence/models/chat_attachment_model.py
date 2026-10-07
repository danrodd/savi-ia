from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UtcDateTime, UuidType


class ChatAttachmentModel(Base):
    """Metadata de una imagen adjunta. Los bytes están en `chat_attachment_blobs`."""

    __tablename__ = "chat_attachments"

    id: Mapped[UUID] = mapped_column(UuidType, primary_key=True, default=uuid4)
    # Mismo criterio que `conversations`: `idUsuario` del ERP + base de
    # identidad (el id solo se repite entre clientes).
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_erp_database_id: Mapped[UUID] = mapped_column(
        UuidType, ForeignKey("erp_databases.id"), nullable=False
    )
    # NULL = subida pero todavía no enviada en un mensaje.
    message_id: Mapped[UUID | None] = mapped_column(
        UuidType,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=True,
    )
    mime: Mapped[str] = mapped_column(String(32), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_chat_attachments_message", "message_id"),
        # Limpieza oportunista de huérfanos por dueño.
        Index("ix_chat_attachments_owner_created", "user_id", "created_at"),
    )


class ChatAttachmentBlobModel(Base):
    """Bytes de la imagen. En tabla aparte para que listar no cargue bytes."""

    __tablename__ = "chat_attachment_blobs"

    attachment_id: Mapped[UUID] = mapped_column(
        UuidType,
        ForeignKey("chat_attachments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
