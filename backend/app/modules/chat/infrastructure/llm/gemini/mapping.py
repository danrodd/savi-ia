from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from google.genai import types

from app.modules.chat.domain.entities import ToolResult
from app.modules.conversations.domain.value_objects import TokenUsage


def _value(metadata: Any, name: str) -> int:
    if isinstance(metadata, Mapping):
        return int(cast(Mapping[str, Any], metadata).get(name) or 0)
    return int(getattr(metadata, name, 0) or 0)


def usage_from_metadata(metadata: Any) -> TokenUsage:
    prompt = _value(metadata, "prompt_token_count")
    cached = _value(metadata, "cached_content_token_count")
    return TokenUsage(
        input_tokens=max(prompt - cached, 0),
        output_tokens=_value(metadata, "candidates_token_count")
        + _value(metadata, "thoughts_token_count"),
        cache_read_input_tokens=cached,
    )


def add_usage(total: TokenUsage, metadata: Any) -> TokenUsage:
    current = usage_from_metadata(metadata)
    return TokenUsage(
        input_tokens=total.input_tokens + current.input_tokens,
        output_tokens=total.output_tokens + current.output_tokens,
        cache_read_input_tokens=total.cache_read_input_tokens
        + current.cache_read_input_tokens,
        cache_creation_input_tokens=total.cache_creation_input_tokens
        + current.cache_creation_input_tokens,
    )


def function_response_part(name: str, result: ToolResult) -> types.Part:
    key = "error" if result.is_error else "result"
    return types.Part.from_function_response(name=name, response={key: result.text})
