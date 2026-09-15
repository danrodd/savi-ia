"""Traduce las `ToolSpec` neutrales a un MCP server in-process del SDK."""

from typing import Any

from claude_agent_sdk import McpSdkServerConfig, SdkMcpTool, create_sdk_mcp_server, tool

from app.modules.chat.domain.entities import ToolSpec

MCP_SERVER_NAME = "savi"
MCP_SERVER_VERSION = "0.5.0"


def _to_sdk_tool(spec: ToolSpec) -> SdkMcpTool[Any]:
    # Un JSON Schema completo (`type` + `properties`) pasa intacto al
    # modelo: el SDK solo traduce el formato abreviado `{campo: tipo}`.
    @tool(spec.name, spec.description, spec.parameters)
    async def _impl(args: dict[str, Any]) -> dict[str, Any]:
        result = await spec.handler(args)
        # `is_error` (snake_case) es la clave que lee el SDK al armar el
        # `CallToolResult`; `isError` se ignoraba en silencio.
        return {
            "content": [{"type": "text", "text": result.text}],
            "is_error": result.is_error,
        }

    return _impl


def build_mcp_server(tools: list[ToolSpec]) -> McpSdkServerConfig:
    return create_sdk_mcp_server(
        name=MCP_SERVER_NAME,
        version=MCP_SERVER_VERSION,
        tools=[_to_sdk_tool(spec) for spec in tools],
    )


def allowed_tool_names(tools: list[ToolSpec]) -> list[str]:
    """Whitelist derivada del registro: no se puede registrar una tool y
    olvidarse de habilitarla."""
    return [f"mcp__{MCP_SERVER_NAME}__{spec.name}" for spec in tools]


# Herramientas integradas del CLI, observadas en el mensaje `init` con las
# opciones reales del chat. `tools=[]` ya las apaga todas; esta lista es la
# segunda barrera por si un CLI futuro cambia el default de `--tools`.
BUILTIN_TOOLS: tuple[str, ...] = (
    "Task",
    "Bash",
    "Edit",
    "Glob",
    "Grep",
    "NotebookEdit",
    "Read",
    "Skill",
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskOutput",
    "TaskStop",
    "TaskUpdate",
    "ToolSearch",
    "WebFetch",
    "WebSearch",
    "Write",
)
