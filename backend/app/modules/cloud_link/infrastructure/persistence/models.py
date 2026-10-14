"""Tablas de la vinculación con SAVI Cloud (BD del agente)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.types import JsonType, UtcDateTime, UuidType


class CloudLinkModel(Base):
    """Una sola fila (`id = 1`)."""

    __tablename__ = "cloud_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    cloud_url: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    instance_id: Mapped[UUID | None] = mapped_column(UuidType, nullable=True)
    client_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Fernet con `ERP_CREDENTIALS_KEY`, igual que las credenciales del ERP.
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Se genera la primera vez que el módulo se usa, ANTES de vincular, y se
    # conserva al desvincular.
    pseudonym_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    install_id: Mapped[UUID] = mapped_column(UuidType, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unlinked")
    policy: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    notices: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, nullable=False, default=list)
    linked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_heartbeat_ok_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    secret_rotated_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    # Solo códigos cortos: nunca mensajes libres que puedan filtrar datos.
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (CheckConstraint("id = 1", name="ck_cloud_link_singleton"),)


class CloudSyncWatermarkModel(Base):
    __tablename__ = "cloud_sync_watermarks"

    stream: Mapped[str] = mapped_column(String(32), primary_key=True)
    watermark_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    watermark_id: Mapped[str] = mapped_column(String(64), nullable=False)
    last_ok_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
