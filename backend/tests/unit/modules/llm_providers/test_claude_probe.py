from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

from claude_agent_sdk import ResultMessage

from app.infrastructure.config import Settings
from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.value_objects import CredentialKind, ProviderKind
from app.modules.llm_providers.infrastructure.probes.claude_probe import ClaudeProbe


@dataclass
class _FakePage:
    _data: list[object]

    @property
    def data(self) -> list[object]:
        return self._data


@dataclass
class _FakeModels:
    data: list[object]
    error: Exception | None = None

    async def list(self, *, limit: int) -> _FakePage:
        assert limit == 100
        if self.error is not None:
            raise self.error
        return _FakePage(self.data)


@dataclass
class _FakeClient:
    _models: _FakeModels

    @property
    def models(self) -> _FakeModels:
        return self._models


def _config(
    kind: CredentialKind = CredentialKind.API_KEY,
    *,
    title_model: str = "claude-haiku-4-5",
) -> LlmProviderConfig:
    return LlmProviderConfig(
        provider=ProviderKind.CLAUDE,
        credential_kind=kind,
        credential="secret",
        chat_model="claude-sonnet-4-6",
        title_model=title_model,
    )


async def test_list_models_maps_anthropic_models() -> None:
    clients: list[tuple[CredentialKind, str]] = []

    def factory(kind: CredentialKind, credential: str) -> _FakeClient:
        clients.append((kind, credential))
        return _FakeClient(
            _FakeModels(
                [
                    SimpleNamespace(id="claude-sonnet-4-6", display_name="Claude Sonnet"),
                    SimpleNamespace(id="claude-haiku-4-5", display_name="Claude Haiku"),
                ]
            )
        )

    probe = ClaudeProbe(Settings(agent_db_engine="sqlite"), client_factory=factory)

    models = await probe.list_models(_config())

    assert [(model.id, model.display_name) for model in models] == [
        ("claude-sonnet-4-6", "Claude Sonnet"),
        ("claude-haiku-4-5", "Claude Haiku"),
    ]
    assert clients == [(CredentialKind.API_KEY, "secret")]


async def test_list_models_excludes_retired_generations() -> None:
    probe = ClaudeProbe(
        Settings(agent_db_engine="sqlite"),
        client_factory=lambda _kind, _credential: _FakeClient(
            _FakeModels(
                [
                    SimpleNamespace(id="claude-sonnet-4-6", display_name="Claude Sonnet"),
                    SimpleNamespace(id="claude-2.1", display_name="Claude 2.1"),
                    SimpleNamespace(id="claude-instant-1.2", display_name="Claude Instant"),
                ]
            )
        ),
    )

    models = await probe.list_models(_config())

    assert [model.id for model in models] == ["claude-sonnet-4-6"]


async def test_list_models_uses_auth_token_for_oauth() -> None:
    clients: list[tuple[CredentialKind, str]] = []
    probe = ClaudeProbe(
        Settings(agent_db_engine="sqlite"),
        client_factory=lambda kind, credential: (
            clients.append((kind, credential)) or _FakeClient(_FakeModels([]))
        ),
    )

    assert await probe.list_models(_config(CredentialKind.OAUTH_TOKEN)) == []
    assert clients == [(CredentialKind.OAUTH_TOKEN, "secret")]


async def test_list_models_returns_empty_for_local_session_and_errors() -> None:
    probe = ClaudeProbe(
        Settings(agent_db_engine="sqlite"),
        client_factory=lambda _kind, _credential: _FakeClient(
            _FakeModels([], error=RuntimeError("catalog unavailable"))
        ),
    )

    assert await probe.list_models(_config(CredentialKind.LOCAL_SESSION)) == []
    assert await probe.list_models(_config()) == []


async def test_test_includes_models_from_direct_catalog() -> None:
    async def fake_query(*, prompt: str, options: object) -> AsyncIterator[ResultMessage]:
        assert prompt == "ping"
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="test-session",
        )

    with patch(
        "app.modules.llm_providers.infrastructure.probes.claude_probe.query", fake_query
    ):
        probe = ClaudeProbe(
            Settings(agent_db_engine="sqlite"),
            client_factory=lambda _kind, _credential: _FakeClient(
                _FakeModels([SimpleNamespace(id="claude-sonnet-4-6", display_name="Sonnet")])
            ),
        )
        result = await probe.test(_config())

    assert result.ok is True
    assert [(model.id, model.display_name) for model in result.models] == [
        ("claude-sonnet-4-6", "Sonnet")
    ]


async def test_test_lists_models_without_running_cli_when_title_model_is_empty() -> None:
    async def unexpected_query(*, prompt: str, options: object) -> AsyncIterator[ResultMessage]:
        raise AssertionError("Claude CLI should not run without a title model")
        yield  # pragma: no cover

    with patch(
        "app.modules.llm_providers.infrastructure.probes.claude_probe.query", unexpected_query
    ):
        probe = ClaudeProbe(
            Settings(agent_db_engine="sqlite"),
            client_factory=lambda _kind, _credential: _FakeClient(
                _FakeModels([SimpleNamespace(id="claude-sonnet-4-6", display_name="Sonnet")])
            ),
        )
        result = await probe.test(_config(title_model=""))

    assert result.ok is True
    assert result.models[0].id == "claude-sonnet-4-6"


async def test_local_session_requires_model_without_catalog() -> None:
    probe = ClaudeProbe(Settings(agent_db_engine="sqlite"))

    result = await probe.test(_config(CredentialKind.LOCAL_SESSION, title_model=""))

    assert result.ok is False
    assert "no expone un catálogo" in result.detail
