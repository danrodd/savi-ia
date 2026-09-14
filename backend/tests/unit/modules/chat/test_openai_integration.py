from __future__ import annotations

from types import SimpleNamespace

import pytest

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
from app.modules.chat.infrastructure.llm.openai.mapping import usage_from_response
from app.modules.chat.infrastructure.llm.openai.runner import OpenAIRunner
from app.modules.chat.infrastructure.llm.openai.title_generator import OpenAITitleGenerator


def _provider() -> ActiveProvider:
    return ActiveProvider(
        kind="openai",
        chat_model="gpt-5.6-terra",
        title_model="gpt-5.6-luna",
        credential_kind="api_key",
        credential="test-key",
        pricing={"gpt-5.6-terra": ModelPrice(input=1, output=2)},
    )


def _usage(input_tokens: int = 10, output_tokens: int = 4, cached: int = 0):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=cached),
    )


def _completed(usage=None):
    return SimpleNamespace(
        type="response.completed",
        response=SimpleNamespace(usage=usage or _usage(), incomplete_details=None),
    )


def _text(delta: str):
    return SimpleNamespace(type="response.output_text.delta", delta=delta)


def _function_call(name: str, call_id: str, arguments: str):
    return SimpleNamespace(
        type="response.output_item.done",
        item=SimpleNamespace(
            type="function_call",
            name=name,
            call_id=call_id,
            arguments=arguments,
            id=f"fc_{call_id}",
        ),
    )


class _Responses:
    def __init__(self, streams: list[list[object]]) -> None:
        self.streams = streams
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object):
        self.calls.append(kwargs)
        stream = self.streams.pop(0)

        async def iterator():
            for event in stream:
                yield event

        return iterator()


class _Client:
    def __init__(self, streams: list[list[object]]) -> None:
        self.responses = _Responses(streams)


@pytest.mark.asyncio
async def test_runner_streams_text_and_done(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.openai.runner.build_savi_tools",
        lambda **_: [],
    )
    client = _Client([[_text("Hola "), _text("mundo"), _completed(_usage(10, 4, 2))]])
    runner = OpenAIRunner(Settings(), _provider(), client=client)

    events = [event async for event in runner.stream_turn("consulta")]

    assert [e.text for e in events if isinstance(e, TextDeltaEvent)] == ["Hola ", "mundo"]
    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.provider == "openai"
    assert done.model == "gpt-5.6-terra"
    assert done.usage == {
        "input_tokens": 8,
        "output_tokens": 4,
        "cache_read_input_tokens": 2,
        "cache_creation_input_tokens": 0,
    }


@pytest.mark.asyncio
async def test_runner_executes_tool_and_resends_output_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def handler(args: dict[str, object]):
        from app.modules.chat.domain.entities import ToolResult

        calls.append(str(args["n"]))
        return ToolResult(f"resultado-{args['n']}")

    tool = ToolSpec("lookup", "lookup", {"type": "object"}, handler)
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.openai.runner.build_savi_tools",
        lambda **_: [tool],
    )
    client = _Client(
        [
            [_function_call("lookup", "call_1", '{"n": 7}'), _completed()],
            [_text("listo"), _completed()],
        ]
    )
    runner = OpenAIRunner(Settings(), _provider(), client=client)

    events = [event async for event in runner.stream_turn("consulta")]

    assert calls == ["7"]
    use = next(e for e in events if isinstance(e, ToolUseEvent))
    assert use.name == "lookup" and use.id == "call_1" and use.input == {"n": 7}
    assert isinstance(
        next(e for e in events if isinstance(e, ToolResultEvent)), ToolResultEvent
    )
    # El segundo request recibe el item de la llamada y su output.
    second_input = client.responses.calls[1]["input"]
    assert isinstance(second_input, list)
    assert second_input[1].type == "function_call"
    assert second_input[2]["type"] == "function_call_output"
    assert second_input[2]["call_id"] == "call_1"
    assert second_input[2]["output"] == "resultado-7"


@pytest.mark.asyncio
async def test_runner_surfaces_credential_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.openai.runner.build_savi_tools",
        lambda **_: [],
    )

    class _AuthResponses:
        async def create(self, **_: object):
            error = RuntimeError("unauthorized")
            error.status_code = 401  # type: ignore[attr-defined]
            raise error

    client = SimpleNamespace(responses=_AuthResponses())
    events = [
        event
        async for event in OpenAIRunner(Settings(), _provider(), client=client).stream_turn(
            "consulta"
        )
    ]

    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert "API key de OpenAI" in error.message


@pytest.mark.asyncio
async def test_runner_falls_back_before_first_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.openai.runner.build_savi_tools",
        lambda **_: [],
    )

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("asyncio.sleep", no_sleep)

    class _FallbackResponses:
        def __init__(self) -> None:
            self.models: list[str] = []

        async def create(self, **kwargs: object):
            model = str(kwargs["model"])
            self.models.append(model)

            async def events():
                if model == "gpt-5.6-terra":
                    error = RuntimeError("overloaded")
                    error.status_code = 503  # type: ignore[attr-defined]
                    raise error
                yield _text("ok")
                yield _completed()

            return events()

    responses = _FallbackResponses()
    client = SimpleNamespace(responses=responses)
    settings = Settings(
        openai_retry_attempts=1,
        openai_retry_base_delay_s=0,
        openai_fallback_models="gpt-5.6-luna",
    )

    events = [
        event
        async for event in OpenAIRunner(settings, _provider(), client=client).stream_turn(
            "consulta"
        )
    ]

    # Un intento de retry sobre el modelo primario antes de caer al fallback.
    assert responses.models[0] == "gpt-5.6-terra"
    assert responses.models[-1] == "gpt-5.6-luna"
    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.model == "gpt-5.6-luna"


def test_usage_mapping_subtracts_cached_from_input() -> None:
    usage = usage_from_response(_usage(input_tokens=100, output_tokens=20, cached=40))

    assert usage.input_tokens == 60
    assert usage.output_tokens == 20
    assert usage.cache_read_input_tokens == 40


@pytest.mark.asyncio
async def test_runner_does_not_retry_when_quota_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.openai.runner.build_savi_tools",
        lambda **_: [],
    )

    class _QuotaResponses:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **_: object):
            self.calls += 1
            error = RuntimeError("no credits")
            error.status_code = 429  # type: ignore[attr-defined]
            error.body = {  # type: ignore[attr-defined]
                "code": "credit_balance_exhausted",
                "type": "insufficient_quota",
            }
            raise error

    responses = _QuotaResponses()
    client = SimpleNamespace(responses=responses)
    settings = Settings(openai_retry_attempts=3, openai_fallback_models="gpt-5.6-luna")

    events = [
        event
        async for event in OpenAIRunner(settings, _provider(), client=client).stream_turn(
            "consulta"
        )
    ]

    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert "créditos" in error.message
    assert responses.calls == 1


@pytest.mark.asyncio
async def test_title_generator_cleans_output() -> None:
    class _TitleResponses:
        async def create(self, **_: object):
            return SimpleNamespace(output_text='"Consulta de facturas."')

    client = SimpleNamespace(responses=_TitleResponses())
    generator = OpenAITitleGenerator(Settings(), _provider(), client=client)

    assert await generator.generate("¿facturas?") == "Consulta de facturas"


@pytest.mark.asyncio
async def test_title_generator_returns_none_on_error() -> None:
    class _FailingResponses:
        async def create(self, **_: object):
            raise RuntimeError("boom")

    client = SimpleNamespace(responses=_FailingResponses())
    generator = OpenAITitleGenerator(Settings(), _provider(), client=client)

    assert await generator.generate("¿facturas?") is None


@pytest.mark.asyncio
async def test_runner_refusal_becomes_error_not_empty_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.openai.runner.build_savi_tools",
        lambda **_: [],
    )
    refusal = SimpleNamespace(type="response.refusal.done", refusal="no puedo")
    client = _Client([[refusal, _completed()]])

    events = [
        event
        async for event in OpenAIRunner(Settings(), _provider(), client=client).stream_turn(
            "consulta"
        )
    ]

    assert any(isinstance(e, ErrorEvent) for e in events)
    assert not any(isinstance(e, DoneEvent) for e in events)


@pytest.mark.asyncio
async def test_runner_response_failed_reads_response_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.openai.runner.build_savi_tools",
        lambda **_: [],
    )
    failed = SimpleNamespace(
        type="response.failed",
        response=SimpleNamespace(error=SimpleNamespace(code=400, message="bad request")),
    )
    client = _Client([[failed]])

    events = [
        event
        async for event in OpenAIRunner(Settings(), _provider(), client=client).stream_turn(
            "consulta"
        )
    ]

    assert any(isinstance(e, ErrorEvent) for e in events)
    assert not any(isinstance(e, DoneEvent) for e in events)


@pytest.mark.asyncio
async def test_runner_multiple_tools_keep_order_and_call_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(args: dict[str, object]):
        from app.modules.chat.domain.entities import ToolResult

        return ToolResult(f"ok-{args['n']}")

    tool = ToolSpec("lookup", "lookup", {"type": "object"}, handler)
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.openai.runner.build_savi_tools",
        lambda **_: [tool],
    )
    client = _Client(
        [
            [
                _function_call("lookup", "call_a", '{"n": 1}'),
                _function_call("lookup", "call_b", '{"n": 2}'),
                _completed(),
            ],
            [_text("listo"), _completed()],
        ]
    )

    events = [
        event
        async for event in OpenAIRunner(Settings(), _provider(), client=client).stream_turn(
            "consulta"
        )
    ]

    uses = [e for e in events if isinstance(e, ToolUseEvent)]
    assert [u.id for u in uses] == ["call_a", "call_b"]
    second = client.responses.calls[1]["input"]
    outputs = [
        item
        for item in second
        if isinstance(item, dict) and item.get("type") == "function_call_output"
    ]
    assert [item["call_id"] for item in outputs] == ["call_a", "call_b"]


@pytest.mark.asyncio
async def test_runner_preserves_reasoning_items_in_next_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(args: dict[str, object]):
        from app.modules.chat.domain.entities import ToolResult

        return ToolResult("ok")

    tool = ToolSpec("lookup", "lookup", {"type": "object"}, handler)
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.openai.runner.build_savi_tools",
        lambda **_: [tool],
    )
    reasoning = SimpleNamespace(
        type="response.output_item.done",
        item=SimpleNamespace(type="reasoning", id="rs_1"),
    )
    client = _Client(
        [
            [reasoning, _function_call("lookup", "call_1", "{}"), _completed()],
            [_text("listo"), _completed()],
        ]
    )

    _ = [
        event
        async for event in OpenAIRunner(Settings(), _provider(), client=client).stream_turn(
            "consulta"
        )
    ]

    second = client.responses.calls[1]["input"]
    assert second[1].type == "reasoning"
    assert second[2].type == "function_call"


@pytest.mark.asyncio
async def test_runner_max_turns_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(args: dict[str, object]):
        from app.modules.chat.domain.entities import ToolResult

        return ToolResult("ok")

    tool = ToolSpec("lookup", "lookup", {"type": "object"}, handler)
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.openai.runner.build_savi_tools",
        lambda **_: [tool],
    )
    client = _Client(
        [
            [_function_call("lookup", "call_1", "{}"), _completed()],
            [_function_call("lookup", "call_2", "{}"), _completed()],
        ]
    )
    runner = OpenAIRunner(Settings(max_agent_turns=2), _provider(), client=client)

    events = [event async for event in runner.stream_turn("consulta")]

    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.finish_reason == "truncated"
