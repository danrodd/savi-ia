from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.types import JsonType, UtcDateTime, UuidType


class ResultSetModel(Base):
    """Filas completas de una consulta al ERP, para la vista previa y la exportación.

    Se borra con la conversación (`ON DELETE CASCADE`) y vence a los 90 días.
    """

    __tablename__ = "result_sets"

    id: Mapped[UUID] = mapped_column(UuidType, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        UuidType, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, nullable=False)
    rows: Mapped[list[list[Any]]] = mapped_column(JsonType, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    total_is_lower_bound: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_personal_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    __table_args__ = (
        Index("ix_result_sets_conversation_created", "conversation_id", "created_at"),
    )
