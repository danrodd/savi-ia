from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UtcDateTime, UuidType
from app.modules.feedback.domain.value_objects import COMMENT_MAX_LENGTH


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MessageFeedbackModel(Base):
    __tablename__ = "message_feedback"

    id: Mapped[UUID] = mapped_column(UuidType, primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(
        UuidType,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Identidad del autor: el `idUsuario` se repite entre clientes, así que
    # siempre va junto con la base con la que inició sesión.
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_erp_database_id: Mapped[UUID] = mapped_column(
        UuidType,
        ForeignKey("erp_databases.id"),
        nullable=False,
    )
    rating: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Código y nombre del usuario al calificar (el panel no puede consultarlos
    # al ERP de cada cliente solo para mostrar una tabla).
    user_login: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=_utc_now, onupdate=_utc_now
    )

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_feedback_message_user"),
        CheckConstraint("rating IN ('up', 'down')", name="ck_message_feedback_rating"),
        CheckConstraint(
            "reason IS NULL OR reason IN "
            "('dato_incorrecto', 'no_entendio', 'incompleta', 'muy_lenta', 'otra')",
            name="ck_message_feedback_reason",
        ),
        # El motivo solo existe con 👎.
        CheckConstraint(
            "reason IS NULL OR rating = 'down'", name="ck_message_feedback_reason_requires_down"
        ),
        CheckConstraint(
            f"comment IS NULL OR length(comment) <= {COMMENT_MAX_LENGTH}",
            name="ck_message_feedback_comment_length",
        ),
        # Panel del administrador: su base, más reciente primero.
        Index("ix_message_feedback_owner_created", "owner_erp_database_id", "created_at"),
        Index("ix_message_feedback_message", "message_id"),
    )
