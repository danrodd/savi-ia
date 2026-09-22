"""Responses del módulo. **Ninguna incluye la credencial.**"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.modules.llm_providers.application.dtos import LlmProviderDTO
from app.modules.llm_providers.application.requests import ModelPricingPayload
from app.modules.llm_providers.domain.interfaces import ProbeResult
from app.modules.llm_providers.domain.value_objects import ModelInfo


class LlmProviderResponse(BaseModel):
    provider: str
    display_name: str
    implemented: bool
    credential_kinds: list[str]
    supports_model_listing: bool
    reports_cost: bool
    configured: bool
    credential_kind: str | None
    has_credential: bool
    credentials_unreadable: bool
    chat_model: str | None
    title_model: str | None
    pricing: dict[str, ModelPricingPayload]
    is_active: bool
    last_test_ok_at: datetime | None

    @classmethod
    def from_dto(cls, dto: LlmProviderDTO) -> LlmProviderResponse:
        return cls(
            provider=dto.provider,
            display_name=dto.display_name,
            implemented=dto.implemented,
            credential_kinds=list(dto.credential_kinds),
            supports_model_listing=dto.supports_model_listing,
            reports_cost=dto.reports_cost,
            configured=dto.configured,
            credential_kind=dto.credential_kind,
            has_credential=dto.has_credential,
            credentials_unreadable=dto.credentials_unreadable,
            chat_model=dto.chat_model,
            title_model=dto.title_model,
            pricing={
                model: ModelPricingPayload(
                    input=p.input,
                    output=p.output,
                    cache_read=p.cache_read,
                    cache_write=p.cache_write,
                )
                for model, p in dto.pricing.items()
            },
            is_active=dto.is_active,
            last_test_ok_at=dto.last_test_ok_at,
        )


class ModelInfoResponse(BaseModel):
    id: str
    display_name: str

    @classmethod
    def from_value(cls, model: ModelInfo) -> ModelInfoResponse:
        return cls(id=model.id, display_name=model.display_name)


class ProviderTestResponse(BaseModel):
    ok: bool
    detail: str
    models: list[ModelInfoResponse] = []

    @classmethod
    def from_result(cls, result: ProbeResult) -> ProviderTestResponse:
        return cls(
            ok=result.ok,
            detail=result.detail,
            models=[ModelInfoResponse.from_value(m) for m in result.models],
        )


class ModelListResponse(BaseModel):
    models: list[ModelInfoResponse]
