from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from google.genai import types

from app.infrastructure.config import Settings
from app.modules.chat.domain.entities import (
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolResultEvent,
    ToolSpec,
    ToolUseEvent,
)
from app.modules.chat.domain.interfaces import ActiveProvider, ModelPrice
from app.modules.chat.infrastructure.llm.gemini.mapping import usage_from_metadata
from app.modules.chat.infrastructure.llm.gemini.runner import GeminiRunner
from app.modules.chat.infrastructure.llm.gemini.title_generator import GeminiTitleGenerator
from app.modules.chat.infrastructure.llm.pricing import compute_cost_usd
from app.modules.conversations.domain.entities import Message, MessageRole
from app.modules.conversations.domain.value_objects import TokenUsage
from app.modules.conversations.infrastructure.persistence.mappers import ConversationOrmMapper
from app.modules.conversations.infrastructure.persistence.models import MessageModel
from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.value_objects import CredentialKind, ProviderKind
from app.modules.llm_providers.infrastructure.probes.gemini_probe import GeminiProbe


def _provider() -> ActiveProvider:
    return ActiveProvider(
        kind="gemini",
        chat_model="gemini-test",
        title_model="gemini-title-test",
        credential_kind="api_key",
        credential="test-key",
        pricing={"gemini-test": ModelPrice(input=1, output=2)},
    )


class _Models:
    def __init__(self, streams: list[list[object]]) -> None:
        self.streams = streams
        self.calls: list[list[types.Content]] = []

    async def generate_content_stream(self, **kwargs: object):
        contents = kwargs["contents"]
        assert isinstance(contents, list)
        self.calls.append(contents)
        stream = self.streams.pop(0)

        async def iterator():
            for chunk in stream:
                yield chunk

        return iterator()


class _Client:
    def __init__(self, streams: list[list[object]]) -> None:
        self.aio = SimpleNamespace(models=_Models(streams))


def _chunk(*parts: types.Part, usage: object | None = None) -> object:
    return SimpleNamespace(
        candidates=[
            SimpleNamespace(content=SimpleNamespace(parts=list(parts)), finish_reason=None)
        ],
        usage_metadata=usage,
    )


class _StatusError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"status {code}")
        self.code = code


class _ScriptedModels:
    def __init__(self, scripts: list[tuple[str, object]]) -> None:
        self.scripts = scripts
        self.calls: list[str] = []

    async def generate_content_stream(self, **kwargs: object):
        model = str(kwargs["model"])
        self.calls.append(model)
        expected_model, result = self.scripts.pop(0)
        assert model == expected_model

        async def iterator():
            if isinstance(result, Exception):
                raise result
            yield result

        return iterator()


@pytest.mark.asyncio
async def test_runner_streams_text_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools",
        lambda **_: [],
    )
    client = _Client(
        [
            [
                _chunk(
                    types.Part.from_text(text="Hola "),
                    usage=SimpleNamespace(prompt_token_count=5, candidates_token_count=2),
                ),
                _chunk(
                    types.Part.from_text(text="mundo"),
                    usage=SimpleNamespace(prompt_token_count=5, candidates_token_count=2),
                ),
            ]
        ]
    )
    runner = GeminiRunner(Settings(), _provider(), client=client)

    events = [event async for event in runner.stream_turn("consulta")]

    assert [event.text for event in events if isinstance(event, TextDeltaEvent)] == [
        "Hola ",
        "mundo",
    ]
    done = next(event for event in events if isinstance(event, DoneEvent))
    assert done.usage == {
        "input_tokens": 5,
        "output_tokens": 2,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    assert done.provider == "gemini"


@pytest.mark.asyncio
async def test_runner_executes_tool_calls_in_order_and_reuses_model_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def handler(args: dict[str, object]):
        calls.append(str(args["n"]))
        from app.modules.chat.domain.entities import ToolResult

        return ToolResult(f"r{args['n']}")

    tool = ToolSpec("lookup", "lookup", {"type": "object"}, handler)
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools",
        lambda **_: [tool],
    )
    model_part = types.Part(
        function_call=types.FunctionCall(name="lookup", args={"n": 1}, id="a"),
        thought_signature=b"sig",
    )
    client = _Client([[_chunk(model_part)], [_chunk(types.Part.from_text(text="listo"))]])
    runner = GeminiRunner(Settings(), _provider(), client=client)

    events = [event async for event in runner.stream_turn("consulta")]

    assert calls == ["1"]
    assert isinstance(
        next(event for event in events if isinstance(event, ToolUseEvent)), ToolUseEvent
    )
    assert isinstance(
        next(event for event in events if isinstance(event, ToolResultEvent)), ToolResultEvent
    )
    assert client.aio.models.calls[1][1].parts[0].thought_signature == b"sig"


@pytest.mark.asyncio
async def test_runner_max_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools",
        lambda **_: [],
    )
    part = types.Part(function_call=types.FunctionCall(name="missing", args={}))
    client = _Client([[_chunk(part)], [_chunk(part)]])
    runner = GeminiRunner(Settings(max_agent_turns=2), _provider(), client=client)

    events = [event async for event in runner.stream_turn("consulta")]

    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "truncated"


@pytest.mark.asyncio
async def test_runner_retries_rate_limit_before_first_token_and_surfaces_auth_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools",
        lambda **_: [],
    )

    class RateLimitModels(_Models):
        def generate_content_stream(self, **kwargs: object):
            if len(self.calls) == 0:
                self.calls.append([])

                class RateLimitError(Exception):
                    code = 429

                async def fail():
                    raise RateLimitError("quota")
                    yield  # pragma: no cover

                return fail()
            return super().generate_content_stream(**kwargs)

    models = RateLimitModels([[_chunk(types.Part.from_text(text="ok"))]])
    client = SimpleNamespace(aio=SimpleNamespace(models=models))

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    events = [
        event
        async for event in GeminiRunner(Settings(), _provider(), client=client).stream_turn(
            "consulta"
        )
    ]
    assert any(isinstance(event, DoneEvent) for event in events)


@pytest.mark.asyncio
async def test_runner_retries_three_times_before_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools",
        lambda **_: [],
    )
    models = _ScriptedModels(
        [
            ("gemini-test", _StatusError(503)),
            ("gemini-test", _StatusError(503)),
            ("gemini-test", _StatusError(503)),
            ("gemini-test", _chunk(types.Part.from_text(text="ok"))),
        ]
    )
    monkeypatch.setattr("asyncio.sleep", lambda _: _noop())
    events = [
        event
        async for event in GeminiRunner(
            Settings(gemini_retry_base_delay_s=0),
            _provider(),
            client=SimpleNamespace(aio=SimpleNamespace(models=models)),
        ).stream_turn("consulta")
    ]
    assert models.calls == ["gemini-test"] * 4
    assert any(isinstance(event, DoneEvent) for event in events)


async def _noop() -> None:
    return None


@pytest.mark.asyncio
async def test_runner_falls_back_after_primary_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools",
        lambda **_: [],
    )
    models = _ScriptedModels(
        [
            ("gemini-test", _StatusError(503)),
            ("gemini-test", _StatusError(503)),
            ("fallback", _chunk(types.Part.from_text(text="ok"))),
        ]
    )
    settings = Settings(
        gemini_retry_attempts=1,
        gemini_retry_base_delay_s=0,
        gemini_fallback_models="fallback, gemini-test, fallback",
    )
    events = [
        event
        async for event in GeminiRunner(
            settings,
            ActiveProvider(
                kind="gemini",
                chat_model="gemini-test",
                title_model="title",
                credential_kind="api_key",
                credential="test-key",
                pricing={"fallback": ModelPrice(input=3, output=4)},
            ),
            client=SimpleNamespace(aio=SimpleNamespace(models=models)),
        ).stream_turn("consulta")
    ]
    assert models.calls == ["gemini-test", "gemini-test", "fallback"]
    assert next(event for event in events if isinstance(event, DoneEvent)).model == "fallback"


@pytest.mark.asyncio
async def test_runner_emits_neutral_error_when_all_models_are_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools",
        lambda **_: [],
    )
    models = _ScriptedModels(
        [
            ("gemini-test", _StatusError(429)),
            ("gemini-test", _StatusError(429)),
            ("fallback", _StatusError(503)),
            ("fallback", _StatusError(503)),
        ]
    )
    events = [
        event
        async for event in GeminiRunner(
            Settings(
                gemini_retry_attempts=1,
                gemini_retry_base_delay_s=0,
                gemini_fallback_models="fallback",
            ),
            _provider(),
            client=SimpleNamespace(aio=SimpleNamespace(models=models)),
        ).stream_turn("consulta")
    ]
    error = next(event for event in events if isinstance(event, ErrorEvent))
    assert error.message == "No pude generar una respuesta para esa consulta."


@pytest.mark.asyncio
async def test_runner_surfaces_gemini_credential_remedy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools",
        lambda **_: [],
    )

    class AuthModels:
        async def generate_content_stream(self, **_: object):
            class AuthError(Exception):
                code = 401

            async def fail():
                raise AuthError("unauthorized")
                yield  # pragma: no cover

            return fail()

    client = SimpleNamespace(aio=SimpleNamespace(models=AuthModels()))
    events = [
        event
        async for event in GeminiRunner(Settings(), _provider(), client=client).stream_turn(
            "consulta"
        )
    ]

    error = next(event for event in events if isinstance(event, ErrorEvent))
    assert "API key de Gemini" in error.message


def test_usage_mapping_and_pricing() -> None:
    usage = usage_from_metadata(
        {
            "prompt_token_count": 10,
            "cached_content_token_count": 3,
            "candidates_token_count": 4,
            "thoughts_token_count": 2,
        }
    )
    assert usage == TokenUsage(input_tokens=7, output_tokens=6, cache_read_input_tokens=3)
    assert compute_cost_usd(usage, ModelPrice(input=1, output=2, cache_read=3)) == pytest.approx(
        0.000028
    )
    assert compute_cost_usd(usage, None) is None


@pytest.mark.asyncio
async def test_title_generator_cleans_title() -> None:
    async def generate_content(**_: object) -> object:
        return SimpleNamespace(text='"Ventas del mes."')

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    generator = GeminiTitleGenerator(Settings(), _provider(), client=client)
    assert await generator.generate("Ventas") == "Ventas del mes"


@pytest.mark.asyncio
async def test_probe_filters_generate_content_models() -> None:
    models = [
        SimpleNamespace(
            name="models/gemini-a",
            display_name="A",
            supported_actions=["generateContent"],
        ),
        SimpleNamespace(
            name="models/embed",
            display_name="Embed",
            supported_actions=["embedContent"],
        ),
    ]

    async def list_models() -> object:
        class Pager:
            def __aiter__(self):
                return self._items()

            async def _items(self):
                for item in models:
                    yield item

        return Pager()

    config = LlmProviderConfig(
        ProviderKind.GEMINI,
        CredentialKind.API_KEY,
        "chat",
        "title",
        "key",
    )
    probe = GeminiProbe(
        client_factory=lambda _: SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(list=list_models))
        )
    )
    result = await probe.test(config)
    assert result.ok is True
    assert [model.id for model in result.models] == ["gemini-a"]


def test_message_provider_and_model_map_to_orm() -> None:
    message = Message(
        uuid4(),
        uuid4(),
        MessageRole.ASSISTANT,
        "ok",
        provider="gemini",
        model="gemini-test",
    )
    model = ConversationOrmMapper.message_to_model(message)
    assert isinstance(model, MessageModel)
    assert model.provider == "gemini"
    assert model.model == "gemini-test"


# ── Cuota y saldo: el mismo 429 pide cosas distintas ─────────────────────


class _QuotaError(Exception):
    """Misma forma que el 429 real de Gemini capturado el 2026-09-28."""

    def __init__(self, message: str, quota_id: str | None = None) -> None:
        super().__init__(message)
        self.code = 429
        self.message = message
        self.details = (
            {"error": {"details": [{"violations": [{"quotaId": quota_id}]}]}} if quota_id else None
        )


def _quota_runner(models: _ScriptedModels, fallback: str = "") -> GeminiRunner:
    return GeminiRunner(
        Settings(
            gemini_retry_attempts=2,
            gemini_retry_base_delay_s=0,
            gemini_fallback_models=fallback,
        ),
        _provider(),
        client=SimpleNamespace(aio=SimpleNamespace(models=models)),
    )


@pytest.mark.asyncio
async def test_without_credits_it_stops_at_once_and_says_what_to_do(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools", lambda **_: []
    )
    models = _ScriptedModels(
        [("gemini-test", _QuotaError("429 Your prepayment credits are depleted."))]
    )

    events = [event async for event in _quota_runner(models, "fallback").stream_turn("hola")]

    # Sin reintentos ni cambio de modelo: ninguno carga saldo.
    assert models.calls == ["gemini-test"]
    error = next(event for event in events if isinstance(event, ErrorEvent))
    assert "no tiene créditos" in error.message


@pytest.mark.asyncio
async def test_an_exhausted_daily_quota_moves_to_the_next_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools", lambda **_: []
    )
    daily = _QuotaError(
        "You exceeded your current quota, please check your plan and billing details.",
        "GenerateRequestsPerDayPerProjectPerModel",
    )
    models = _ScriptedModels(
        [("gemini-test", daily), ("fallback", _chunk(types.Part.from_text(text="ok")))]
    )

    events = [event async for event in _quota_runner(models, "fallback").stream_turn("hola")]

    assert models.calls == ["gemini-test", "fallback"]
    assert any(isinstance(event, DoneEvent) for event in events)


@pytest.mark.asyncio
async def test_without_more_models_the_daily_quota_is_explained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools", lambda **_: []
    )
    daily = _QuotaError("quota", "GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    models = _ScriptedModels([("gemini-test", daily)])

    events = [event async for event in _quota_runner(models).stream_turn("hola")]

    error = next(event for event in events if isinstance(event, ErrorEvent))
    assert "cuota diaria" in error.message


@pytest.mark.asyncio
async def test_the_per_minute_limit_is_still_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """El mensaje real dice "billing" aunque sea el límite por minuto."""
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools", lambda **_: []
    )
    per_minute = _QuotaError(
        "You exceeded your current quota, please check your plan and billing details.",
        "GenerateRequestsPerMinutePerProjectPerModel",
    )
    models = _ScriptedModels(
        [("gemini-test", per_minute), ("gemini-test", _chunk(types.Part.from_text(text="ok")))]
    )

    events = [event async for event in _quota_runner(models).stream_turn("hola")]

    assert models.calls == ["gemini-test", "gemini-test"]
    assert any(isinstance(event, DoneEvent) for event in events)
