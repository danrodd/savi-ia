"""Entidades de la lectura de PDF por página (Fase 4).

La lectura decide página por página si se usa la capa de texto o la IA.
En la Fase 4 la política siempre responde "IA" cuando está disponible; la
Fase 5 solo cambia esa política, con las métricas que se guardan acá.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.modules.company_knowledge.domain.value_objects.reading import (
    AiReadErrorCode,
    AiReadOutcome,
    PageRoute,
)


@dataclass(frozen=True, slots=True)
class PageMetrics:
    """Lo que `pypdf` sabe de una página, sin gastar nada.

    `text` es el texto ya normalizado y sin líneas repetidas (marcas de
    agua, encabezados); sirve de respaldo si la IA falla. No se persiste.
    """

    page_number: int
    text: str
    image_count: int = 0
    max_image_pixels: int = 0

    @property
    def pypdf_chars(self) -> int:
        return len(self.text)


@dataclass(frozen=True, slots=True)
class PdfAnalysis:
    """Resultado de analizar un PDF completo con `pypdf`."""

    pages: list[PageMetrics]

    @property
    def page_count(self) -> int:
        return len(self.pages)


@dataclass(frozen=True, slots=True)
class AiPageContent:
    """Una página transcrita por la IA, ya validada contra el esquema."""

    page_number: int
    page_type: str
    content: str
    legible: bool


@dataclass(frozen=True, slots=True)
class AiReadUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    # `None` si el modelo no tiene precio configurado.
    cost_usd: float | None = None


@dataclass(frozen=True, slots=True)
class AiReadResult:
    """Respuesta del proveedor para un tramo."""

    pages: list[AiPageContent]
    usage: AiReadUsage = field(default_factory=AiReadUsage)


@dataclass(frozen=True, slots=True)
class ReadPage:
    """Página leída de una versión del documento, lista para persistir."""

    page_number: int
    method: PageRoute
    text: str
    pypdf_chars: int = 0
    image_count: int = 0
    max_image_pixels: int = 0
    page_type: str | None = None
    legible: bool | None = None
    ai_error: AiReadErrorCode | None = None
    prompt_version: int | None = None


@dataclass(frozen=True, slots=True)
class AiReadRecord:
    """Registro de gasto de un pedido al proveedor. No lleva contenido."""

    document_id: UUID
    version: int
    page_from: int
    page_to: int
    provider: str
    model: str
    outcome: AiReadOutcome
    uploaded_by_login: str
    uploaded_by_database_id: UUID | None
    usage: AiReadUsage = field(default_factory=AiReadUsage)
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeSettings:
    """Configuración del módulo. Una sola por instalación.

    La lectura con IA manda los PDF completos al proveedor, así que viene
    apagada y necesita que un administrador acepte el envío a un proveedor
    concreto. Aceptar uno no autoriza a otro: si cambia el proveedor activo,
    no se manda nada hasta aceptar el nuevo.
    """

    ai_reading_enabled: bool = False
    updated_by_login: str | None = None
    updated_at: datetime | None = None
    consent_provider: str | None = None
    consent_by_login: str | None = None
    consent_at: datetime | None = None
    # Subidas, reemplazos y lecturas de sitios por usuario y por hora.
    # `None`: el valor por defecto del servidor.
    upload_limit_per_hour: int | None = None

    def allows_sending_to(self, provider: str | None) -> bool:
        return (
            self.ai_reading_enabled and provider is not None and self.consent_provider == provider
        )
