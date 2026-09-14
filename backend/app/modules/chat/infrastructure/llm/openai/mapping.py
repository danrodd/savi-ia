"""Traducciones entre el contrato neutral de SAVI y la Responses API.

Todo lo específico de OpenAI vive acá: definición de tools, mapeo de
`usage` y la forma del `function_call_output`. El runner solo emite
eventos del dominio.
"""
from __future__ import annotations

from typing import Any

from app.modules.chat.domain.entities import ToolResult, ToolSpec
from app.modules.conversations.domain.value_objects import TokenUsage


def _value(source: Any, name: str) -> int:
    if source is None:
        return 0
    return int(getattr(source, name, 0) or 0)


def usage_from_response(usage: Any) -> TokenUsage:
    """Convierte el `usage` de Responses al canónico de SAVI.

    OpenAI reporta `input_tokens` incluyendo los que salieron de caché, así
    que el caché se resta del input y se informa aparte, igual que con
    Gemini. Los reasoning tokens ya vienen dentro de `output_tokens`.
    """
    input_tokens = _value(usage, "input_tokens")
    cached = _value(getattr(usage, "input_tokens_details", None), "cached_tokens")
    return TokenUsage(
        input_tokens=max(input_tokens - cached, 0),
        output_tokens=_value(usage, "output_tokens"),
        cache_read_input_tokens=cached,
    )


def add_usage(total: TokenUsage, usage: Any) -> TokenUsage:
    current = usage_from_response(usage)
    return TokenUsage(
        input_tokens=total.input_tokens + current.input_tokens,
        output_tokens=total.output_tokens + current.output_tokens,
        cache_read_input_tokens=total.cache_read_input_tokens
        + current.cache_read_input_tokens,
        cache_creation_input_tokens=total.cache_creation_input_tokens
        + current.cache_creation_input_tokens,
    )


def tool_definitions(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Traduce las `ToolSpec` neutrales al formato de function calling.

    `strict=False` a propósito: las schemas neutrales pueden tener campos
    opcionales que no cumplen los requisitos de strict mode. Endurecerlo
    es una fase posterior, con tests por tool.
    """
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "strict": False,
        }
        for tool in tools
    ]


def function_call_output(call_id: str, result: ToolResult) -> dict[str, Any]:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": result.text,
    }
