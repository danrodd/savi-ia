"""Modelo ORM para `agent_db.audit_query`.

Persiste cada intento de consulta libre — ok, rechazado por el validador
AST, por el EXPLAIN gate, por rate limit, o que falló en BD. Sirve para:
- detectar patrones de abuso multi-turno (mismo conversation_id con
  muchas queries rechazadas o de alto cost),
- auditoría post-hoc (qué pidió el usuario, qué SQL salió),
- métricas de uso del Nivel D (cuánto se usa SQL libre vs semantic).
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class AuditQueryModel(Base):
    __tablename__ = "audit_query"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # Si el turno se hizo fuera de una conversación (futuro), queda NULL.
    conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    # Pregunta del usuario en lenguaje natural, truncada a 500 chars para
    # no inflar la tabla. El LLM la pasa como argumento de la tool.
    user_question: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # SQL final que se intentó ejecutar (post-normalización con LIMIT
    # ajustado), o el SQL crudo si fue rechazado en AST.
    sql: Mapped[str] = mapped_column(Text, nullable=False)
    # Resultado del intento — codificado, indexable.
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    estimated_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    returned_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_audit_query_conversation_created", "conversation_id", "created_at"),
        Index("ix_audit_query_result_created", "result", "created_at"),
    )
