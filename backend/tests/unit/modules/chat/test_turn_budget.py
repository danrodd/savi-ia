"""Presupuesto del turno: tope de consultas al ERP y de texto por tool.

En la demo un turno hizo 14 consultas y los siguientes fallaron con OpenAI por
el volumen de contexto. El tope corta antes y le dice al modelo qué hacer.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.chat.domain.entities import ToolResult
from app.modules.chat.infrastructure.llm.tools import registry
from app.modules.chat.infrastructure.llm.tools.turn_budget import TurnBudget


def test_queries_stop_at_the_limit() -> None:
    budget = TurnBudget(max_queries=2, max_chars=100)

    assert budget.take_query() is None
    assert budget.take_query() is None
    refused = budget.take_query()

    assert refused is not None and refused.is_error
    assert "responde con los datos que ya tienes" in refused.text


def test_a_long_result_is_cut_with_a_notice() -> None:
    budget = TurnBudget(max_queries=2, max_chars=10)

    fitted = budget.fit(ToolResult(text="x" * 50))

    assert fitted.text.startswith("x" * 10)
    assert "Resultado recortado" in fitted.text
    assert budget.fit(ToolResult(text="corto")).text == "corto"


async def test_the_tools_share_the_budget_and_the_query_does_not_reach_the_erp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_consultar_datos(args: dict[str, Any], **_: Any) -> dict[str, Any]:
        calls.append(args)
        return {"content": [{"type": "text", "text": "filas"}]}

    monkeypatch.setattr(registry, "consultar_datos_impl", fake_consultar_datos)
    monkeypatch.setattr(registry, "get_catalog", lambda: None)
    monkeypatch.setattr(
        registry, "build_consultar_conocimiento_impl", lambda *_: fake_consultar_datos
    )
    monkeypatch.setattr(
        registry,
        "get_settings",
        lambda: type("S", (), {"erp_queries_per_turn": 3, "tool_result_max_chars": 1000})(),
    )
    tools = registry.build_savi_tools(
        conversation_id=None, allowed_modules=frozenset(), erp_database_id=None
    )
    consultar = next(t for t in tools if t.name == "consultar_datos")

    results = [await consultar.handler({"n": i}) for i in range(5)]

    assert len(calls) == 3
    assert [r.is_error for r in results] == [False, False, False, True, True]


def test_two_permission_denials_stop_further_queries() -> None:
    from app.modules.data_query.application.permission_text import permission_denied_text

    budget = TurnBudget(max_queries=12, max_chars=10_000)
    denied = ToolResult(text=permission_denied_text({"celular": ("TERCERO",)}))

    assert budget.take_query() is None
    budget.fit(denied)
    assert budget.take_query() is None
    budget.fit(denied)
    refused = budget.take_query()

    assert refused is not None and "dos rechazos" in refused.text
