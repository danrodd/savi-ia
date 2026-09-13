"""Modelo ORM para `agent_db.erp_databases`.

Registro de las conexiones a las BD de los clientes del ERP. Vive en la
BD del agente (SQLite en escritorio, Postgres en servidor), no en el
ERP: es configuración de SAVI, no dato del cliente.

La contraseña se guarda cifrada (Fernet, ver `FernetCredentialCipher`) y
nunca sale del backend.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UtcDateTime, UuidType


class ErpDatabaseModel(Base):
    __tablename__ = "erp_databases"

    id: Mapped[UUID] = mapped_column(UuidType, primary_key=True, default=uuid4)
    # Identificador corto del cliente: lo que va después del `@` en el
    # login calificado. Validado con `^[A-Z0-9_-]{2,32}$`, charset que
    # excluye el `@` para que el `rsplit` del login no sea ambiguo.
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=5432)
    database: Mapped[str] = mapped_column(String(120), nullable=False)
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    # Token Fernet en base64 urlsafe. `Text` y no `String(n)`: el largo
    # depende del de la contraseña y no conviene acotarlo.
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    statement_timeout_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60000, server_default="60000"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    # Se marca cuando el descifrado falla: la clave cambió o se perdió.
    # La base queda inutilizable hasta re-ingresar la contraseña, pero la
    # aplicación arranca igual en vez de morir con un error de cripto.
    credentials_unreadable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_connection_ok_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime, nullable=True
    )
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
        # Los tres únicos son PARCIALES (`WHERE deleted_at IS NULL`): una
        # base eliminada no debe bloquear que se registre otra con el
        # mismo código o nombre.
        #
        # SQLite soporta índices parciales, pero se crean por dos caminos
        # distintos (`create_all` en BD nueva, `alembic upgrade` en
        # existente) y hay que verificarlos en ambos: si el de `code` no
        # se creara, el síntoma no sería un error sino un código
        # duplicado que rompe el login en silencio.
        Index(
            "uq_erp_databases_code",
            "code",
            unique=True,
            sqlite_where=deleted_at.is_(None),
            postgresql_where=deleted_at.is_(None),
        ),
        Index(
            "uq_erp_databases_name",
            "name",
            unique=True,
            sqlite_where=deleted_at.is_(None),
            postgresql_where=deleted_at.is_(None),
        ),
        Index(
            "uq_erp_databases_default",
            "is_default",
            unique=True,
            sqlite_where=deleted_at.is_(None) & is_default.is_(True),
            postgresql_where=deleted_at.is_(None) & is_default.is_(True),
        ),
        Index("ix_erp_databases_active", "deleted_at", "is_active"),
    )
