"""Regression test: el MCP server NO debe exceder el límite de tools.

Por qué este test existe: el Claude Agent SDK pasa a modo "deferred
tools" cuando hay más de ~5-6 tools registradas, lo que confunde al
LLM y produce alucinaciones tipo "la herramienta no responde" aunque
las tools sí devolvieran datos válidos. Esto nos costó una tarde de
debugging en junio 2026.

Si este test falla porque agregaste una tool nueva, ANTES de subir el
límite leé:

    backend/docs/mcp_deferred_tools_gotcha.md

con el patrón dispatcher (una sola tool con campo `tipo` que rutea
internamente) y el checklist al agregar tools MCP.
"""
from __future__ import annotations

from app.modules.chat.infrastructure.llm.mcp.server import ALLOWED_TOOLS

# Umbral conservador. La constante puede subir SOLO con evidencia
# empírica de que el SDK sigue en modo directo (no aparece ToolSearch
# en tool_invocations, cache_read_input_tokens estable, sin
# alucinaciones del LLM). Ver gotcha doc.
_MAX_MCP_TOOLS = 4


def test_allowed_tools_under_deferred_threshold() -> None:
    """ALLOWED_TOOLS no debe exceder el límite. Si necesitás más
    funcionalidades, consolidá con dispatcher pattern."""
    count = len(ALLOWED_TOOLS)
    assert count <= _MAX_MCP_TOOLS, (
        f"ALLOWED_TOOLS tiene {count} entradas (máximo permitido: "
        f"{_MAX_MCP_TOOLS}). Riesgo ALTO de deferred tools mode del "
        "Claude Agent SDK. Leé backend/docs/mcp_deferred_tools_gotcha.md "
        "para el patrón dispatcher (una tool con campo `tipo` que rutea "
        "internamente)."
    )


def test_allowed_tools_no_duplicates() -> None:
    """Garantiza que ALLOWED_TOOLS no tenga duplicados accidentales."""
    assert len(ALLOWED_TOOLS) == len(set(ALLOWED_TOOLS)), (
        "ALLOWED_TOOLS tiene entradas duplicadas — posible merge buggy."
    )
