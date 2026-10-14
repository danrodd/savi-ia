"""ORM de `user_totp` en `agent_db`: una fila por usuario con segundo factor."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UtcDateTime, UuidType


class UserTotpModel(Base):
    __tablename__ = "user_totp"

    # Identidad real del usuario: `idUsuario` solo se repite entre bases de clientes.
    erp_database_id: Mapped[UUID] = mapped_column(UuidType, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Denormalizado para restablecer por login sin consultar el ERP.
    user_login: Mapped[str] = mapped_column(String(50), nullable=False)
    # Cifrado con la misma clave que las contraseñas de las bases del ERP.
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL = configuración pendiente (se mostró el QR pero no se confirmó un código).
    enabled_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_step: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Restablecer por login (`JPEREZ@NORTE`).
        Index("ix_user_totp_login", "erp_database_id", "user_login"),
    )
