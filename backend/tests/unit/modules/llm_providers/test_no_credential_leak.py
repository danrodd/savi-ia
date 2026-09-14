"""Ningún response de `/admin/llm-providers` puede llevar la credencial,
ni en claro ni cifrada.

La garantía es estructural, igual que en `erp_databases`: `LlmProviderDTO`
y `LlmProviderResponse` directamente no tienen el campo `credential`, así
que no depende de que alguien se acuerde de omitirlo al serializar.
"""
from __future__ import annotations

from app.modules.llm_providers.application.dtos import LlmProviderDTO
from app.modules.llm_providers.application.responses import LlmProviderResponse
from app.modules.llm_providers.domain.entities import LlmProviderConfig, get_descriptor
from app.modules.llm_providers.domain.value_objects import CredentialKind, ProviderKind


def _config() -> LlmProviderConfig:
    return LlmProviderConfig(
        provider=ProviderKind.CLAUDE,
        credential_kind=CredentialKind.API_KEY,
        credential="sk-ant-super-secret",
        chat_model="claude-sonnet-4-6",
        title_model="claude-haiku-4-5",
        is_active=True,
    )


def test_dto_has_no_credential_field() -> None:
    dto = LlmProviderDTO.build(get_descriptor("claude"), _config())

    assert not hasattr(dto, "credential")
    assert "sk-ant-super-secret" not in repr(dto)


def test_response_serialization_never_contains_the_credential() -> None:
    dto = LlmProviderDTO.build(get_descriptor("claude"), _config())
    response = LlmProviderResponse.from_dto(dto)

    dumped = response.model_dump_json()

    assert "sk-ant-super-secret" not in dumped
    assert response.has_credential is True
