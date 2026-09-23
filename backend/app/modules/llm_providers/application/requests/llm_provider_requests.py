"""Requests de administración de proveedores de IA.

La credencial **solo** viaja de entrada.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.llm_providers.application.dtos import SaveLlmProviderDTO
from app.modules.llm_providers.domain.value_objects import ModelPricing


class ModelPricingPayload(BaseModel):
    input: float = Field(default=0.0, ge=0)
    output: float = Field(default=0.0, ge=0)
    cache_read: float = Field(default=0.0, ge=0)
    cache_write: float = Field(default=0.0, ge=0)


class SaveLlmProviderRequest(BaseModel):
    credential_kind: str = Field(min_length=1, max_length=32)
    # Vacía = conservar la guardada.
    credential: str = Field(default="", max_length=4096)
    chat_model: str = Field(min_length=1, max_length=120)
    title_model: str = Field(min_length=1, max_length=120)
    # Omitido = conservar el guardado; vacío = usar el modelo de chat.
    document_model: str | None = Field(default=None, max_length=120)
    pricing: dict[str, ModelPricingPayload] | None = None

    def to_dto(self) -> SaveLlmProviderDTO:
        return SaveLlmProviderDTO(
            credential_kind=self.credential_kind,
            credential=self.credential.strip(),
            chat_model=self.chat_model.strip(),
            title_model=self.title_model.strip(),
            document_model=(None if self.document_model is None else self.document_model.strip()),
            pricing=(
                None
                if self.pricing is None
                else {
                    model.strip(): ModelPricing(
                        input=p.input,
                        output=p.output,
                        cache_read=p.cache_read,
                        cache_write=p.cache_write,
                    )
                    for model, p in self.pricing.items()
                    if model.strip()
                }
            ),
        )


class TestLlmProviderRequest(BaseModel):
    credential_kind: str = Field(min_length=1, max_length=32)
    # Vacía = conservar la guardada.
    credential: str = Field(default="", max_length=4096)
    # El catálogo puede probarse antes de elegir los modelos.
    chat_model: str = Field(default="", max_length=120)
    title_model: str = Field(default="", max_length=120)

    def to_dto(self) -> SaveLlmProviderDTO:
        return SaveLlmProviderDTO(
            credential_kind=self.credential_kind,
            credential=self.credential.strip(),
            chat_model=self.chat_model.strip(),
            title_model=self.title_model.strip(),
        )
