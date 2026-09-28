"""Tipos de la importación desde la web (Fase 5)."""

from enum import StrEnum


class DocumentSourceKind(StrEnum):
    """De dónde viene un documento: subido a mano o leído de un sitio web."""

    UPLOAD = "upload"
    WEB = "web"


class WebSourceMode(StrEnum):
    PAGE = "page"  # solo la URL indicada
    SITE = "site"  # la URL raíz y las páginas del mismo sitio


class RefreshFrequency(StrEnum):
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"


class WebSourceStatus(StrEnum):
    PENDING = "pending"  # esperando el primer rastreo o un refresco pedido
    CRAWLING = "crawling"
    READY = "ready"
    FAILED = "failed"


class WebSourceStatusCode(StrEnum):
    """Motivo estable de una fuente `failed` o con aviso."""

    UNSAFE_URL = "unsafe_url"
    ROBOTS_DISALLOWED = "robots_disallowed"
    UNREACHABLE = "unreachable"
    BLOCKED = "blocked"  # anti-bots o login
    NO_PAGES = "no_pages"
    INTERNAL_ERROR = "internal_error"


class WebPageStatus(StrEnum):
    """Resultado de leer una página en el último rastreo."""

    IMPORTED = "imported"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"  # sin texto útil, solo plantilla, duplicada
    FAILED = "failed"  # HTTP 4xx/5xx o error de red
    REMOVED = "removed"  # desapareció dos veces seguidas: se dio de baja
