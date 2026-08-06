"""ORM model de refresh_token en `agent_db`.

Diseño: una fila por refresh emitido. Se setea `revoked_at` en logout
o rotación. NO se borran físicamente (auditoría); un job periódico
puede purgar los expirados/revocados muy viejos si la tabla crece.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UtcDateTime, UuidType


class RefreshTokenModel(Base):
    __tablename__ = "refresh_token"

    # El `jti` es la PK — coincide con el claim del JWT.
    jti: Mapped[UUID] = mapped_column(UuidType, primary_key=True)
    # FK lógica al `idUsuario` del ERP. No es FK física porque el ERP vive
    # en otra BD; se mantiene por integridad lógica del lado de SAVI.
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Denormalizamos el login para no tener que joinear cross-db en
    # auditorías rápidas.
    user_login: Mapped[str] = mapped_column(String(50), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    __table_args__ = (
        # Para revocación masiva por usuario.
        Index("ix_refresh_token_user_id", "user_id"),
        # Para una tarea opcional de purga de tokens viejos.
        Index("ix_refresh_token_expires_at", "expires_at"),
    )
