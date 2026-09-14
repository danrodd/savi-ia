"""Definición neutral de una tool del agente, independiente del proveedor.

Cada proveedor de IA la traduce a su formato: MCP para Claude,
`FunctionDeclaration` para Gemini. Las tools se definen una sola vez y los
permisos por base, el multi-BD y la auditoría quedan compartidos.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolResult:
    text: str
    is_error: bool = False


ToolHandler = Callable[[dict[str, Any]], Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    # JSON Schema del objeto de argumentos (`type: object` + `properties`).
    parameters: dict[str, Any]
    handler: ToolHandler
