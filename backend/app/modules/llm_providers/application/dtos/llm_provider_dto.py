"""DTOs del módulo.

**Ningún DTO de salida lleva la credencial**, ni en claro ni cifrada: el
campo directamente no existe en `LlmProviderDTO`. La regla es
estructural, no depende de que alguien se acuerde de omitirlo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.modules.llm_providers.domain.entities import LlmProviderConfig, ProviderDescriptor
from app.modules.llm_providers.domain.value_objects import ModelPricing


@dataclass(frozen=True, slots=True)
class SaveLlmProviderDTO:
    credential_kind: str
    chat_model: str
    title_model: str
    # `None` = conservar el guardado; vacío = usar el modelo de chat.
    document_model: str | None = None
    # Vacía = conservar la guardada.
    credential: str = ""
    # `None` = conservar los precios guardados.
    pricing: dict[str, ModelPricing] | None = None


@dataclass(frozen=True, slots=True)
class LlmProviderDTO:
    provider: str
    display_name: str
    implemented: bool
    credential_kinds: tuple[str, ...]
    supports_model_listing: bool
    reports_cost: bool
    configured: bool
    credential_kind: str | None
    has_credential: bool
    credentials_unreadable: bool
    chat_model: str | None
    title_model: str | None
    document_model: str | None
    pricing: dict[str, ModelPricing]
    is_active: bool
    last_test_ok_at: datetime | None

    @classmethod
    def build(
        cls, descriptor: ProviderDescriptor, config: LlmProviderConfig | None
    ) -> LlmProviderDTO:
        return cls(
            provider=descriptor.kind.value,
            display_name=descriptor.display_name,
            implemented=descriptor.implemented,
            credential_kinds=tuple(k.value for k in descriptor.credential_kinds),
            supports_model_listing=descriptor.supports_model_listing,
            reports_cost=descriptor.reports_cost,
            configured=config is not None,
            credential_kind=config.credential_kind.value if config else None,
            has_credential=config.has_credential if config else False,
            credentials_unreadable=config.credentials_unreadable if config else False,
            chat_model=config.chat_model if config else None,
            title_model=config.title_model if config else None,
            document_model=config.document_model if config else None,
            pricing=dict(config.pricing) if config else {},
            is_active=config.is_active if config else False,
            last_test_ok_at=config.last_test_ok_at if config else None,
        )
