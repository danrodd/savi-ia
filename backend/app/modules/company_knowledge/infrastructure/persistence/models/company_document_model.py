"""Modelos ORM para `agent_db` del módulo `company_knowledge`.

Documento, su alcance por base, el blob original, los fragmentos con sus
vectores y, desde la lectura con IA, las páginas leídas, el registro de
gasto y la configuración del módulo. Los bytes de `embedding` son `float32`
little-endian normalizados (`dim × 4`), portables entre Postgres y SQLite
sin extensiones.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
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
    reading_method: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ai_page_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    ai_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
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
    # Fase 5: `web` = página de una fuente web, citada con su URL.
    source_kind: Mapped[str] = mapped_column(
        String(8), nullable=False, default="upload", server_default="upload"
    )
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
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


class CompanyDocumentPageModel(Base):
    """Página leída de una versión del documento.

    Guarda el texto final (de `pypdf` o de la IA) y las métricas de `pypdf`
    que deciden el modo mixto de la Fase 5.
    """

    __tablename__ = "company_document_pages"

    document_id: Mapped[UUID] = mapped_column(
        UuidType,
        ForeignKey("company_documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    page_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    legible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    pypdf_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_image_pixels: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    ai_error: Mapped[str | None] = mapped_column(String(48), nullable=True)
    prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )


class CompanyDocumentAiReadModel(Base):
    """Un pedido al proveedor de IA para leer un tramo. Sin contenido.

    Sin FK al documento: el gasto queda registrado aunque el documento se
    dé de baja.
    """

    __tablename__ = "company_document_ai_reads"

    id: Mapped[UUID] = mapped_column(UuidType, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(UuidType, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    page_from: Mapped[int] = mapped_column(Integer, nullable=False)
    page_to: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    uploaded_by_login: Mapped[str] = mapped_column(String(50), nullable=False)
    uploaded_by_database_id: Mapped[UUID | None] = mapped_column(UuidType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_company_document_ai_reads_created_at", "created_at", "provider"),
        Index("ix_company_document_ai_reads_document", "document_id", "version"),
    )


class CompanyKnowledgeSettingsModel(Base):
    """Configuración del módulo. Una sola fila (`id = 1`)."""

    __tablename__ = "company_knowledge_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ai_reading_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    updated_by_login: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Proveedor al que un administrador aceptó enviar los PDF, quién y cuándo.
    ai_reading_consent_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_reading_consent_by_login: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_reading_consent_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CompanyWebSourceModel(Base):
    """Fuente web (Fase 5): una página o un sitio que SAVI lee y refresca."""

    __tablename__ = "company_web_sources"

    id: Mapped[UUID] = mapped_column(UuidType, primary_key=True, default=uuid4)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    refresh: Mapped[str] = mapped_column(String(8), nullable=False)
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_sections: Mapped[list[str]] = mapped_column(
        JsonType, nullable=False, default=list, server_default="[]"
    )
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    modules: Mapped[list[str]] = mapped_column(
        JsonType, nullable=False, default=list, server_default="[]"
    )
    all_databases: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    status_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_crawl_started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_crawl_finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    next_refresh_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_by_login: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_database_id: Mapped[UUID] = mapped_column(
        UuidType, ForeignKey("erp_databases.id"), nullable=False
    )
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    __table_args__ = (Index("ix_company_web_sources_status", "status", "created_at"),)


class CompanyWebSourceDatabaseModel(Base):
    """Alcance por base de la fuente. Solo hay filas cuando `all_databases = false`."""

    __tablename__ = "company_web_source_databases"

    source_id: Mapped[UUID] = mapped_column(
        UuidType, ForeignKey("company_web_sources.id", ondelete="CASCADE"), primary_key=True
    )
    erp_database_id: Mapped[UUID] = mapped_column(
        UuidType, ForeignKey("erp_databases.id"), primary_key=True
    )


class CompanyWebPageModel(Base):
    """Página de una fuente y el documento que la representa."""

    __tablename__ = "company_web_pages"

    document_id: Mapped[UUID] = mapped_column(
        UuidType, ForeignKey("company_documents.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[UUID] = mapped_column(
        UuidType, ForeignKey("company_web_sources.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    status_detail: Mapped[str | None] = mapped_column(String(300), nullable=True)
    etag: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    missing_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_fetched_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_changed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    __table_args__ = (Index("ix_company_web_pages_source", "source_id", "url", unique=True),)
