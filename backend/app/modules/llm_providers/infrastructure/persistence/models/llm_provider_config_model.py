"""Modelo ORM para `agent_db.llm_provider_configs`.

Una fila por proveedor de IA. La credencial se guarda cifrada con la
misma clave que las contraseñas del ERP (`ERP_CREDENTIALS_KEY`) y nunca
sale del backend.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.types import JsonType, UtcDateTime, UuidType


class LlmProviderConfigModel(Base):
    __tablename__ = "llm_provider_configs"

    id: Mapped[UUID] = mapped_column(UuidType, primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    credential_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Token Fernet. `NULL` con `local_session`: no hay nada que guardar.
    credential_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Se marca cuando el descifrado falla (cambió la clave). El proveedor
    # queda inutilizable hasta re-ingresar la credencial, pero la
    # aplicación arranca igual. Mismo patrón que `erp_databases`.
    credentials_unreadable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    chat_model: Mapped[str] = mapped_column(String(120), nullable=False)
    title_model: Mapped[str] = mapped_column(String(120), nullable=False)
    # Lectura de documentos con IA. `NULL` = usar `chat_model`.
    document_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # `{ "<model_id>": { "input", "output", "cache_read", "cache_write" } }`
    # en USD por millón de tokens.
    pricing: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict, server_default="{}"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_test_ok_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Único PARCIAL: a lo sumo un proveedor activo. Se verifica en los
        # dos caminos de SQLite (`create_all` y `upgrade`), igual que los
        # de `erp_databases`.
        Index(
            "uq_llm_provider_configs_active",
            "is_active",
            unique=True,
            sqlite_where=is_active.is_(True),
            postgresql_where=is_active.is_(True),
        ),
    )
