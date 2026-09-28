from enum import StrEnum


class PageRoute(StrEnum):
    """Con qué se lee una página: la capa de texto (`pypdf`) o la IA."""

    TEXT = "text"
    AI = "ai"


class ReadingMethod(StrEnum):
    """Cómo quedó leído un documento completo."""

    TEXT = "text"
    AI = "ai"
    MIXED = "mixed"


class AiReadOutcome(StrEnum):
    """Resultado de un pedido al proveedor para leer un tramo."""

    OK = "ok"
    RETRIED = "retried"
    FALLBACK = "fallback"


class AiReadErrorCode(StrEnum):
    """Motivo estable por el que una página cayó al respaldo de `pypdf`.

    Va en `company_document_pages.ai_error`; no cambia el estado del
    documento.
    """

    UNAVAILABLE = "ai_unavailable"
    INVALID_JSON = "ai_invalid_json"
    RATE_LIMITED = "ai_rate_limited"
    # La cuenta del proveedor no tiene saldo; reintentar no lo arregla.
    NO_CREDITS = "ai_no_credits"
    # Gemini: la cuota diaria del modelo se agotó; vuelve al día siguiente.
    DAILY_QUOTA = "ai_daily_quota"
    TIMEOUT = "ai_timeout"
    PAGE_TOO_LARGE = "page_too_large"
    MISSING_PAGE = "ai_missing_page"
    PROVIDER_ERROR = "ai_error"
