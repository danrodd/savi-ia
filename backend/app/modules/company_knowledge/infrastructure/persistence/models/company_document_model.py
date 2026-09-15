"""Modelos ORM para `agent_db` del módulo `company_knowledge`.

Cuatro tablas: documento, su alcance por base, el blob original y los
fragmentos con sus vectores. Los bytes de `embedding` son `float32`
little-endian normalizados (`dim × 4`), portables entre Postgres y SQLite
sin extensiones.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.types import JsonType, UtcDateTime, UuidType


class CompanyDocumentModel(Base):
    __tablename__ = "company_documents"

    id: Mapped[UUID] = mapped_column(UuidType, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    status_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    modules: Mapped[list[str]] = mapped_column(
        JsonType, nullable=False, default=list, server_default="[]"
    )
    all_databases: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    uploaded_by_login: Mapped[str] = mapped_column(String(50), nullable=False)
    uploaded_by_database_id: Mapped[UUID] = mapped_column(
        UuidType, ForeignKey("erp_databases.id"), nullable=False
    )
    uploaded_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # Único PARCIAL: un archivo eliminado no bloquea volver a subirlo.
        Index(
            "uq_company_documents_sha256",
            "sha256",
            unique=True,
            sqlite_where=deleted_at.is_(None),
            postgresql_where=deleted_at.is_(None),
        ),
        Index("ix_company_documents_status", "status", "created_at"),
    )


class CompanyDocumentDatabaseModel(Base):
    """Alcance por base. Solo hay filas cuando `all_databases = false`."""

    __tablename__ = "company_document_databases"

    document_id: Mapped[UUID] = mapped_column(
        UuidType,
        ForeignKey("company_documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    erp_database_id: Mapped[UUID] = mapped_column(
        UuidType, ForeignKey("erp_databases.id"), primary_key=True
    )


class CompanyDocumentBlobModel(Base):
    """Archivo original. En tabla aparte para que listar no cargue bytes."""

    __tablename__ = "company_document_blobs"

    document_id: Mapped[UUID] = mapped_column(
        UuidType,
        ForeignKey("company_documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class CompanyDocumentChunkModel(Base):
    __tablename__ = "company_document_chunks"

    id: Mapped[UUID] = mapped_column(UuidType, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        UuidType,
        ForeignKey("company_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    page_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heading: Mapped[str | None] = mapped_column(String(300), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_company_document_chunks_document_ordinal", "document_id", "ordinal"),
    )
