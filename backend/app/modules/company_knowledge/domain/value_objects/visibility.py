from enum import StrEnum


class DocumentVisibility(StrEnum):
    """Quién puede consultar el documento dentro de una base donde aplica."""

    ALL = "all"
    MODULES = "modules"
    ADMINS = "admins"


class DocumentStatus(StrEnum):
    """Estado del ciclo de vida del documento."""

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    NO_TEXT = "no_text"
    FAILED = "failed"


class DocumentStatusCode(StrEnum):
    """Motivo estable de un estado `failed`/`no_text`."""

    PDF_ENCRYPTED = "pdf_encrypted"
    PDF_UNREADABLE = "pdf_unreadable"
    ENCODING_UNSUPPORTED = "encoding_unsupported"
    TOO_MANY_PAGES = "too_many_pages"
    TOO_MANY_CHUNKS = "too_many_chunks"
    INDEX_LIMIT_REACHED = "index_limit_reached"
    # Leído con IA y ninguna página resultó legible (foto borrosa, etc.).
    AI_UNREADABLE = "ai_unreadable"
    # La IA no respondió (modelo inexistente, clave, saldo, tiempo) y sin
    # ella el PDF no tiene texto.
    AI_FAILED = "ai_failed"
    INTERNAL_ERROR = "internal_error"
