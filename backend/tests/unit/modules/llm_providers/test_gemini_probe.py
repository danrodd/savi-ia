from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.value_objects import CredentialKind, ProviderKind
from app.modules.llm_providers.infrastructure.probes.gemini_probe import GeminiProbe


def _config() -> LlmProviderConfig:
    return LlmProviderConfig(
        provider=ProviderKind.GEMINI,
        credential_kind=CredentialKind.API_KEY,
        credential="test-key",
        chat_model="",
        title_model="",
    )


class _Models:
    async def list(self):
        async def pager():
            for model in (
                SimpleNamespace(
                    name="models/gemini-flash-latest",
                    display_name="Gemini Flash Latest",
                    supported_actions=["generateContent"],
                ),
                SimpleNamespace(
                    name="models/gemini-pro-latest",
                    display_name="Gemini Pro Latest",
                    supported_actions=["generateContent"],
                ),
                SimpleNamespace(
                    name="models/text-embedding-004",
                    display_name="Text Embedding 004",
                    supported_actions=["embedContent"],
                ),
                SimpleNamespace(
                    name="models/gemini-2.5-flash",
                    display_name="Gemini 2.5 Flash",
                    supported_actions=["generateContent"],
                ),
                SimpleNamespace(
                    name="models/gemini-3.1-pro-preview",
                    display_name="Gemini 3.1 Pro Preview",
                    supported_actions=["generateContent"],
                ),
                SimpleNamespace(
                    name="models/lyria-3.5",
                    display_name="Lyria 3.5",
                    supported_actions=["generateContent"],
                ),
                SimpleNamespace(
                    name="models/gemini-2.5-flash-image",
                    display_name="Nano Banana",
                    supported_actions=["generateContent"],
                ),
            ):
                yield model

        return pager()


class _Client:
    def __init__(self) -> None:
        self.aio = SimpleNamespace(models=_Models())


@pytest.mark.asyncio
async def test_list_models_filters_to_chat_eligible_gemini_models() -> None:
    probe = GeminiProbe(client_factory=lambda _: _Client())

    models = await probe.list_models(_config())

    assert [(model.id, model.display_name) for model in models] == [
        ("gemini-flash-latest", "Gemini Flash Latest"),
        ("gemini-pro-latest", "Gemini Pro Latest"),
    ]


@pytest.mark.asyncio
async def test_test_returns_the_model_catalog() -> None:
    probe = GeminiProbe(client_factory=lambda _: _Client())

    result = await probe.test(_config())

    assert result.ok is True
    assert len(result.models) == 2


@pytest.mark.asyncio
async def test_list_models_returns_empty_when_provider_api_fails() -> None:
    class FailingModels:
        async def list(self):
            async def fail():
                raise RuntimeError("network failure")
                yield  # pragma: no cover

            return fail()

    probe = GeminiProbe(
        client_factory=lambda _: SimpleNamespace(aio=SimpleNamespace(models=FailingModels()))
    )

    assert await probe.list_models(_config()) == []
