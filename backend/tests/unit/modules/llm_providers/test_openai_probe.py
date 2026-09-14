from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError

from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.value_objects import CredentialKind, ProviderKind
from app.modules.llm_providers.infrastructure.probes.openai_probe import OpenAIProbe


def _config() -> LlmProviderConfig:
    return LlmProviderConfig(
        provider=ProviderKind.OPENAI,
        credential_kind=CredentialKind.API_KEY,
        credential="test-key",
        chat_model="",
        title_model="",
    )


class _Models:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    async def list(self):
        return SimpleNamespace(data=[SimpleNamespace(id=model_id) for model_id in self._ids])


def _client(ids: list[str]):
    return SimpleNamespace(models=_Models(ids))


@pytest.mark.asyncio
async def test_list_models_filters_non_conversational_and_sorts() -> None:
    probe = OpenAIProbe(
        client_factory=lambda _: _client(
            [
                "gpt-5.6-terra",
                "text-embedding-3-large",
                "whisper-1",
                "gpt-5.6-luna",
                "dall-e-3",
                "o4-mini",
            ]
        )
    )

    models = await probe.list_models(_config())

    assert [model.id for model in models] == [
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "o4-mini",
    ]


@pytest.mark.asyncio
async def test_list_models_keeps_unknown_future_ids() -> None:
    probe = OpenAIProbe(client_factory=lambda _: _client(["gpt-6-omega-future"]))

    models = await probe.list_models(_config())

    assert [model.id for model in models] == ["gpt-6-omega-future"]


@pytest.mark.asyncio
async def test_test_returns_the_catalog() -> None:
    probe = OpenAIProbe(client_factory=lambda _: _client(["gpt-5.6-terra"]))

    result = await probe.test(_config())

    assert result.ok is True
    assert [model.id for model in result.models] == ["gpt-5.6-terra"]


@pytest.mark.asyncio
async def test_invalid_key_is_ok_false_without_raising() -> None:
    class _AuthModels:
        async def list(self):
            response = httpx.Response(
                401, request=httpx.Request("GET", "https://api.openai.com/v1/models")
            )
            raise APIStatusError("unauthorized", response=response, body=None)

    probe = OpenAIProbe(
        client_factory=lambda _: SimpleNamespace(models=_AuthModels())
    )

    result = await probe.test(_config())

    assert result.ok is False
    assert "API key" in result.detail


@pytest.mark.asyncio
async def test_network_failure_returns_empty_catalog() -> None:
    class _FailingModels:
        async def list(self):
            raise RuntimeError("network down")

    probe = OpenAIProbe(
        client_factory=lambda _: SimpleNamespace(models=_FailingModels())
    )

    assert await probe.list_models(_config()) == []
