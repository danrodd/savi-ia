"""Servidor MCP in-process para SAVI.

Se construye uno nuevo por turno (vía `build_savi_mcp_server(conversation_id)`)
para clausurar contexto por turno: hoy solo `conversation_id` (necesario
para el audit log de SQL libre); mañana se agregará el usuario autenticado
y sus permisos.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.modules.chat.infrastructure.llm.mcp.tools.consultar_datos import (
    build_description,
    consultar_datos_impl,
)
from app.modules.chat.infrastructure.llm.mcp.tools.consultar_libre import (
    build_consultar_libre_impl,
)
from app.modules.chat.infrastructure.llm.mcp.tools.info_empresa import (
    info_empresa_impl,
)

MCP_SERVER_NAME = "savi"
MCP_SERVER_VERSION = "0.3.0"


_CONSULTAR_LIBRE_DESCRIPTION = (
    "Ejecuta un SELECT SQL contra la base de datos del ERP del cliente. "
    "Úsalo SOLO cuando `consultar_datos` (semantic layer) no cubra el "
    "caso: preguntas puntuales sobre tablas no modeladas, joins "
    "específicos, agregados ad-hoc.\n\n"
    "Reglas DURAS — si no las respetás, la consulta se rechaza:\n"
    "- Solo UN SELECT por llamada (sin ; multi-statement).\n"
    "- Sin OFFSET. Si necesitás otro subconjunto, afiná filtros.\n"
    "- Sin CTE (WITH), UNION, INTERSECT, EXCEPT, LATERAL.\n"
    "- Sin SELECT * en la raíz: listá las columnas que necesitás.\n"
    "- LIMIT obligatorio ≤ 50 (si lo omitís se inyecta 50; si pones más, "
    "se baja a 50).\n"
    "- El planner debe estimar ≤ 1000 filas; si no, se rechaza por "
    "demasiado amplia.\n"
    "- Subqueries: máximo 2 niveles de anidamiento.\n\n"
    "Estilo recomendado: usá nombres entre comillas dobles para schemas, "
    "tablas y columnas si tienen mayúsculas o caracteres especiales "
    "(ej. \"Empresa\".\"CentroCosto\", \"f.idFactura\"). Postgres distingue "
    "mayúsculas en identifiers quoted.\n\n"
    "Pasá el `pregunta_usuario` original como argumento para auditoría."
)


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


def _build_consultar_datos_tool():
    @tool("consultar_datos", build_description(), {"consulta": dict})
    async def _impl(args: dict[str, Any]) -> dict[str, Any]:
        return await consultar_datos_impl(args)

    return _impl


def _build_consultar_libre_tool(conversation_id: UUID | None):
    impl = build_consultar_libre_impl(conversation_id)

    @tool(
        "consultar_libre",
        _CONSULTAR_LIBRE_DESCRIPTION,
        {"sql": str, "pregunta_usuario": str},
    )
    async def _impl(args: dict[str, Any]) -> dict[str, Any]:
        return await impl(args)

    return _impl


def build_savi_mcp_server(conversation_id: UUID | None = None):
    return create_sdk_mcp_server(
        name=MCP_SERVER_NAME,
        version=MCP_SERVER_VERSION,
        tools=[
            _build_info_empresa_tool(),
            _build_consultar_datos_tool(),
            _build_consultar_libre_tool(conversation_id),
        ],
    )


ALLOWED_TOOLS: list[str] = [
    f"mcp__{MCP_SERVER_NAME}__info_empresa",
    f"mcp__{MCP_SERVER_NAME}__consultar_datos",
    f"mcp__{MCP_SERVER_NAME}__consultar_libre",
]
