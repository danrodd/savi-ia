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

from app.modules.auth.domain.value_objects.module_code import ModuleCode
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
from app.modules.chat.infrastructure.llm.mcp.tools.knowledge import (
    build_consultar_conocimiento_impl,
)
from app.modules.knowledge.infrastructure.catalog_provider import get_catalog

MCP_SERVER_NAME = "savi"
MCP_SERVER_VERSION = "0.4.0"


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
    '(ej. "Empresa"."CentroCosto", "f.idFactura"). Postgres distingue '
    "mayúsculas en identifiers quoted.\n\n"
    "Pasá el `pregunta_usuario` original como argumento para auditoría."
)


def _build_info_empresa_tool(erp_database_id: UUID | None):
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
        return await info_empresa_impl(args, erp_database_id=erp_database_id)

    return _impl


def _build_consultar_datos_tool(erp_database_id: UUID | None):
    @tool("consultar_datos", build_description(), {"consulta": dict})
    async def _impl(args: dict[str, Any]) -> dict[str, Any]:
        return await consultar_datos_impl(args, erp_database_id=erp_database_id)

    return _impl


def _build_consultar_libre_tool(
    conversation_id: UUID | None, erp_database_id: UUID | None
):
    impl = build_consultar_libre_impl(conversation_id, erp_database_id)

    @tool(
        "consultar_libre",
        _CONSULTAR_LIBRE_DESCRIPTION,
        {"sql": str, "pregunta_usuario": str},
    )
    async def _impl(args: dict[str, Any]) -> dict[str, Any]:
        return await impl(args)

    return _impl


_CONSULTAR_CONOCIMIENTO_DESCRIPTION = (
    "Tool ÚNICA para consultar el catálogo de conocimiento del ERP "
    "(módulos, formularios, procesos, workflows, FAQs, glosario). "
    "Llamala SIEMPRE que el usuario pregunte CÓMO hacer algo, DÓNDE "
    "está una funcionalidad, QUÉ pasos involucra un proceso, o por "
    "siglas del dominio.\n\n"
    "Argumentos:\n"
    "- `tipo`: discriminador, uno de:\n"
    "  * 'intencion' (USO POR DEFECTO): busca conceptos del ERP por la "
    "intención natural del usuario. Pasá la consulta tal como la formuló.\n"
    "  * 'modulo': descripción de un módulo. `consulta` = código "
    "(CONTABILIDAD, NÓMINA, INVENTARIO, etc.).\n"
    "  * 'workflow': detalle de un proceso end-to-end. `consulta` = id "
    "del workflow (p.ej. 'wf_ciclo_venta').\n"
    "  * 'faq': pregunta frecuente pre-mapeada. `consulta` = pregunta.\n"
    "  * 'glosario': sigla o término. `consulta` = el término "
    "(DIAN, PILA, NIT, PUC).\n"
    "  * 'modulos_disponibles': lista de módulos del usuario. "
    "`consulta` = '' (vacío).\n"
    "  * 'formulario': lookup directo por nombre interno frmXxx. "
    "`consulta` = nombre del formulario.\n\n"
    "El response trae `matches` (para intencion), `module`, `workflow`, "
    "`faqs`, `entry` o `modules` según el tipo. **Si la respuesta trae "
    "datos, ESOS DATOS SON REALES — usalos para componer tu respuesta. "
    "NUNCA digas que la herramienta no respondió si trae contenido.**"
)


def _build_knowledge_tool(allowed_modules: frozenset[ModuleCode] | None):
    """Construye la tool ÚNICA del knowledge con el catálogo singleton y
    el set de módulos del usuario actual baked-in por clausura.

    Si `allowed_modules` es None, el agente accede a TODO (caso admin
    bypass). Si es un set, la tool filtra al devolver al LLM.

    Mantenemos UNA SOLA tool porque el Claude Agent SDK pasa a modo
    'deferred tools' cuando hay muchas — eso fuerza un ciclo extra de
    discovery y confunde al modelo (síntoma típico: el LLM alucina que
    'el catálogo no responde' aunque la tool sí devolvió matches).
    """
    cat = get_catalog()

    @tool(
        "consultar_conocimiento",
        _CONSULTAR_CONOCIMIENTO_DESCRIPTION,
        {"tipo": str, "consulta": str},
    )
    async def _consultar(args: dict[str, Any]) -> dict[str, Any]:
        impl = build_consultar_conocimiento_impl(cat, allowed_modules)
        return await impl(args)

    return [_consultar]


def build_savi_mcp_server(
    conversation_id: UUID | None = None,
    allowed_modules: frozenset[ModuleCode] | None = None,
    erp_database_id: UUID | None = None,
):
    """Construye el MCP server para un turno.

    `allowed_modules` viene del usuario autenticado (vía ChatTurnUseCase).
    None significa "admin / sin filtro". La tool del knowledge filtra
    contra este set antes de devolver al LLM.

    Total de tools: 4 (info_empresa, consultar_datos, consultar_libre,
    consultar_conocimiento). Mantenemos el número BAJO para evitar
    que el SDK pase a modo 'deferred tools' que confunde al LLM."""
    return create_sdk_mcp_server(
        name=MCP_SERVER_NAME,
        version=MCP_SERVER_VERSION,
        tools=[
            _build_info_empresa_tool(erp_database_id),
            _build_consultar_datos_tool(erp_database_id),
            _build_consultar_libre_tool(conversation_id, erp_database_id),
            *_build_knowledge_tool(allowed_modules),
        ],
    )


ALLOWED_TOOLS: list[str] = [
    f"mcp__{MCP_SERVER_NAME}__info_empresa",
    f"mcp__{MCP_SERVER_NAME}__consultar_datos",
    f"mcp__{MCP_SERVER_NAME}__consultar_libre",
    f"mcp__{MCP_SERVER_NAME}__consultar_conocimiento",
]
