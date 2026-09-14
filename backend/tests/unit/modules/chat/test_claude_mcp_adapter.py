"""Adaptador MCP de Claude: lo que efectivamente le llega al modelo.

Se ejecuta el handler `tools/call` del MCP server que arma el SDK, no
solo nuestra función: es la única forma de ver el `CallToolResult` real,
que es donde estaban los dos defectos (knowledge vacío y errores sin
marcar).
"""
from __future__ import annotations

from typing import Any

from mcp import types

from app.modules.chat.domain.entities import ToolResult, ToolSpec
from app.modules.chat.infrastructure.llm.claude.mcp_adapter import (
    allowed_tool_names,
    build_mcp_server,
)
from app.modules.chat.infrastructure.llm.tools.registry import to_tool_result

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"consulta": {"type": "string"}},
    "required": ["consulta"],
}


def _spec(name: str, raw: dict[str, Any]) -> ToolSpec:
    async def handler(_args: dict[str, Any]) -> ToolResult:
        return to_tool_result(raw)

    return ToolSpec(name=name, description="x", parameters=_SCHEMA, handler=handler)


async def _call(specs: list[ToolSpec], name: str) -> types.CallToolResult:
    server = build_mcp_server(specs)["instance"]
    handler = server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments={"consulta": "factura"}),
    )
    response = await handler(request)
    assert isinstance(response.root, types.CallToolResult)
    return response.root


def test_allowed_tool_names_follow_the_mcp_prefix() -> None:
    specs = [_spec("info_empresa", {}), _spec("consultar_datos", {})]
    assert allowed_tool_names(specs) == [
        "mcp__savi__info_empresa",
        "mcp__savi__consultar_datos",
    ]


async def test_raw_knowledge_result_reaches_the_model_with_content() -> None:
    specs = [_spec("consultar_conocimiento", {"matches": [{"form": "frmFactura"}]})]

    result = await _call(specs, "consultar_conocimiento")

    texts = [c.text for c in result.content if isinstance(c, types.TextContent)]
    assert texts and "frmFactura" in texts[0]
    assert result.isError is False


async def test_tool_error_is_reported_as_error_to_the_model() -> None:
    specs = [
        _spec(
            "consultar_libre",
            {"content": [{"type": "text", "text": "SQL rechazado"}], "isError": True},
        )
    ]

    result = await _call(specs, "consultar_libre")

    assert result.isError is True


async def test_full_json_schema_is_advertised_untouched() -> None:
    server = build_mcp_server([_spec("consultar_conocimiento", {})])["instance"]
    handler = server.request_handlers[types.ListToolsRequest]

    response = await handler(types.ListToolsRequest(method="tools/list"))

    assert isinstance(response.root, types.ListToolsResult)
    assert response.root.tools[0].inputSchema == _SCHEMA
