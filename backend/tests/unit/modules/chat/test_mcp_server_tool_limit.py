"""Regression test: el agente NO debe exceder el límite de tools.

Por qué este test existe: el Claude Agent SDK pasa a modo "deferred
tools" cuando hay más de ~5-6 tools registradas, lo que confunde al
LLM y produce alucinaciones tipo "la herramienta no responde" aunque
las tools sí devolvieran datos válidos. Esto nos costó una tarde de
debugging en junio 2026.

El límite se valida sobre el registro neutral: las tools son las mismas
para todos los proveedores.

Si este test falla porque agregaste una tool nueva, ANTES de subir el
límite leé:

    backend/docs/mcp_deferred_tools_gotcha.md

con el patrón dispatcher (una sola tool con campo `tipo` que rutea
internamente) y el checklist al agregar tools.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.chat.infrastructure.llm.claude.mcp_adapter import allowed_tool_names
from app.modules.chat.infrastructure.llm.tools import registry
from app.modules.chat.infrastructure.llm.tools.registry import build_savi_tools
from app.modules.knowledge.infrastructure.static_catalog import load_static_catalog

# Umbral conservador. La constante puede subir SOLO con evidencia
# empírica de que el SDK sigue en modo directo (no aparece ToolSearch
# en tool_invocations, cache_read_input_tokens estable, sin
# alucinaciones del LLM). Ver gotcha doc.
_MAX_TOOLS = 4


@pytest.fixture
def allowed_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    catalog = load_static_catalog(tmp_path)
    monkeypatch.setattr(registry, "get_catalog", lambda: catalog)
    tools = build_savi_tools(conversation_id=None, allowed_modules=None, erp_database_id=None)
    return allowed_tool_names(tools)


def test_allowed_tools_under_deferred_threshold(allowed_tools: list[str]) -> None:
    """Si necesitás más funcionalidades, consolidá con dispatcher pattern."""
    count = len(allowed_tools)
    assert count <= _MAX_TOOLS, (
        f"El agente tiene {count} tools (máximo permitido: {_MAX_TOOLS}). "
        "Riesgo ALTO de deferred tools mode del Claude Agent SDK. Leé "
        "backend/docs/mcp_deferred_tools_gotcha.md para el patrón dispatcher "
        "(una tool con campo `tipo` que rutea internamente)."
    )


def test_allowed_tools_no_duplicates(allowed_tools: list[str]) -> None:
    assert len(allowed_tools) == len(set(allowed_tools)), (
        "Hay tools duplicadas — posible merge buggy."
    )
