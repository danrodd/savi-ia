"""Servidor MCP in-process para SAVI.

Se construye uno nuevo por turno (vía `build_savi_mcp_server()`) para
permitir, más adelante, capturar contexto por clausura (usuario actual,
permisos, áreas). Hoy es estático porque todavía no tenemos auth.
"""
from __future__ import annotations

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.modules.chat.infrastructure.llm.mcp.tools.info_empresa import (
    info_empresa_impl,
)

MCP_SERVER_NAME = "savi"
MCP_SERVER_VERSION = "0.1.0"


def _build_info_empresa_tool():
    @tool(
        "info_empresa",
        (
            "Devuelve los datos básicos de la empresa registrada en el ERP: "
            "NIT, razón social, dirección, teléfono, correo y representante "
            "legal. Úsala cuando el usuario pregunte por la información de "
            '"mi empresa", "los datos de la empresa", "quién es el '
            'representante legal" o similares.'
        ),
        {},
    )
    async def _impl(args: dict[str, Any]) -> dict[str, Any]:
        return await info_empresa_impl(args)

    return _impl


def build_savi_mcp_server():
    return create_sdk_mcp_server(
        name=MCP_SERVER_NAME,
        version=MCP_SERVER_VERSION,
        tools=[_build_info_empresa_tool()],
    )


ALLOWED_TOOLS: list[str] = [
    f"mcp__{MCP_SERVER_NAME}__info_empresa",
]
