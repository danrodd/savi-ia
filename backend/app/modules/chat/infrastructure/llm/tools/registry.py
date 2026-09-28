"""Registro neutral de las tools del agente, construido por turno.

Por turno y no una sola vez: las clausuras atan el contexto del turno
(conversación para la auditoría de SQL libre, módulos permitidos del
usuario en la base consultada —D3— y la base del ERP). Reutilizar tools
entre turnos cruzaría ese contexto.

Siguen siendo exactamente 4 tools, con el patrón dispatcher en el
knowledge. Ver `backend/docs/mcp_deferred_tools_gotcha.md`.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import UUID

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.chat.domain.entities import ToolResult, ToolSpec
from app.modules.chat.infrastructure.llm.tools.consultar_datos import (
    build_description,
    consultar_datos_impl,
)
from app.modules.chat.infrastructure.llm.tools.consultar_libre import (
    build_consultar_libre_impl,
)
from app.modules.chat.infrastructure.llm.tools.documents import (
    DocumentListing,
    DocumentSearch,
    build_document_listing,
    build_document_search,
)
from app.modules.chat.infrastructure.llm.tools.info_empresa import info_empresa_impl
from app.modules.chat.infrastructure.llm.tools.knowledge import (
    build_consultar_conocimiento_impl,
)
from app.modules.chat.infrastructure.llm.tools.schemas import (
    CONSULTAR_CONOCIMIENTO_SCHEMA,
    CONSULTAR_DATOS_SCHEMA,
    CONSULTAR_LIBRE_SCHEMA,
    INFO_EMPRESA_SCHEMA,
)
from app.modules.company_knowledge.domain.services import TurnDocumentContext
from app.modules.company_knowledge.infrastructure.provider import (
    get_company_knowledge_runtime,
)
from app.modules.data_query.domain.exceptions import SemanticQueryError
from app.modules.free_query.domain.errors import FreeQueryError
from app.modules.knowledge.infrastructure.catalog_provider import get_catalog
from app.shared.exceptions import DomainError

log = logging.getLogger(__name__)

_RawHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

# Errores cuyo texto está escrito PARA el modelo: le dicen qué corregir. El
# resto se le devuelve genérico, porque el mensaje de una excepción cualquiera
# puede traer host, ruta o SQL y el modelo se lo repite al usuario.
_EXPLAINABLE_ERRORS = (FreeQueryError, SemanticQueryError, DomainError)

_INFO_EMPRESA_DESCRIPTION = (
    "Devuelve los datos básicos de la empresa registrada en el ERP: "
    "NIT, razón social, dirección, teléfono, correo y representante "
    "legal. Úsala cuando el usuario pregunte por la información de "
    '"mi empresa", "los datos de la empresa", "quién es el '
    'representante legal" o similares.'
)

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
    "`consulta` = nombre del formulario.\n"
    "  * 'documentos': documentos PROPIOS de la empresa (políticas, "
    "procedimientos, reglamentos, actas, normas internas). `consulta` = la "
    "pregunta del usuario. Cada resultado trae `ref` (D1, D2…): citala entre "
    "corchetes, [D1], justo después de la afirmación que respalda.\n"
    "  * 'documentos_disponibles': lista los títulos de los documentos de la "
    "empresa que el usuario puede consultar. `consulta` = '' (vacío).\n\n"
    "El response trae `matches` (para intencion), `module`, `workflow`, "
    "`faqs`, `entry` o `modules` según el tipo. **Si la respuesta trae "
    "datos, ESOS DATOS SON REALES — usalos para componer tu respuesta. "
    "NUNCA digas que la herramienta no respondió si trae contenido.**"
)


def to_tool_result(raw: dict[str, Any]) -> ToolResult:
    """Normaliza la respuesta de un handler a `ToolResult`.

    Conviven dos formas:
    - Formato MCP (`info_empresa`, `consultar_datos`, `consultar_libre`):
      `{"content": [{"type": "text", "text": ...}], "isError": bool}`.
    - Dict de datos crudo (`consultar_conocimiento`): `{"matches": [...]}`,
      o `{"error": ...}` para un `tipo` desconocido.

    El SDK de Claude solo convertía la primera forma y leía `is_error`: el
    knowledge le llegaba vacío al modelo y ningún error se marcaba como
    tal. Normalizar acá corrige las dos cosas para todos los proveedores.
    """
    content = raw.get("content")
    if isinstance(content, list):
        items = cast(list[Any], content)
        texts = [
            str(cast(dict[str, Any], item).get("text", ""))
            for item in items
            if isinstance(item, dict) and cast(dict[str, Any], item).get("type") == "text"
        ]
        is_error = bool(raw.get("isError") or raw.get("is_error"))
        return ToolResult(text="\n".join(texts), is_error=is_error)
    return ToolResult(
        text=json.dumps(raw, ensure_ascii=False, default=str),
        is_error="error" in raw,
    )


def _spec(name: str, description: str, parameters: dict[str, Any], raw: _RawHandler) -> ToolSpec:
    async def handler(args: dict[str, Any]) -> ToolResult:
        try:
            return to_tool_result(await raw(args))
        except _EXPLAINABLE_ERRORS as e:
            # Los errores TIPADOS del dominio (SQL inválido, consulta muy
            # amplia, entidad desconocida) sí van con su texto: están
            # redactados a propósito para que el modelo se autocorrija, y ya
            # pasaron por su propio saneado.
            log.info("tool_domain_error name=%s error=%s", name, type(e).__name__)
            return ToolResult(text=str(e), is_error=True)
        except Exception:  # noqa: BLE001
            # Un fallo INESPERADO vuelve al modelo como error genérico y no
            # corta el turno. El texto de la excepción no viaja: puede traer
            # host, ruta o SQL, y el modelo lo repite al usuario. El detalle
            # queda en el log, que es donde sirve.
            log.exception("tool_failed name=%s", name)
            return ToolResult(
                text="La herramienta falló por un problema interno. Probá reformular la consulta.",
                is_error=True,
            )

    return ToolSpec(name=name, description=description, parameters=parameters, handler=handler)


def _document_search(document_context: TurnDocumentContext | None) -> DocumentSearch | None:
    """Búsqueda de documentos del turno, o `None` si no hay índice o contexto.

    Sin contexto no hay permisos que aplicar, así que no hay búsqueda: nunca
    se cae a "sin filtro".
    """
    runtime = get_company_knowledge_runtime()
    if runtime is None or document_context is None:
        return None
    return build_document_search(runtime.index, document_context, limit=runtime.search_limit)


def _document_listing(document_context: TurnDocumentContext | None) -> DocumentListing | None:
    runtime = get_company_knowledge_runtime()
    if runtime is None or document_context is None:
        return None
    return build_document_listing(runtime.index, document_context)


def build_savi_tools(
    *,
    conversation_id: UUID | None,
    allowed_modules: frozenset[ModuleCode] | None,
    erp_database_id: UUID | None,
    document_context: TurnDocumentContext | None = None,
) -> list[ToolSpec]:
    """`allowed_modules=None` significa admin sin filtro (D3)."""

    async def info_empresa(args: dict[str, Any]) -> dict[str, Any]:
        return await info_empresa_impl(args, erp_database_id=erp_database_id)

    async def consultar_datos(args: dict[str, Any]) -> dict[str, Any]:
        return await consultar_datos_impl(
            args, erp_database_id=erp_database_id, modules=allowed_modules
        )

    consultar_conocimiento = build_consultar_conocimiento_impl(
        get_catalog(),
        allowed_modules,
        _document_search(document_context),
        _document_listing(document_context),
    )

    tools = [
        _spec("info_empresa", _INFO_EMPRESA_DESCRIPTION, INFO_EMPRESA_SCHEMA, info_empresa),
        _spec(
            "consultar_datos",
            build_description(allowed_modules),
            CONSULTAR_DATOS_SCHEMA,
            consultar_datos,
        ),
        _spec(
            "consultar_conocimiento",
            _CONSULTAR_CONOCIMIENTO_DESCRIPTION,
            CONSULTAR_CONOCIMIENTO_SCHEMA,
            consultar_conocimiento,
        ),
    ]

    # SQL libre SOLO para administradores de la base consultada.
    #
    # La tool no distingue esquemas ni módulos: escribe la consulta que le
    # pidan sobre cualquier tabla del ERP. En manos de un usuario con acceso
    # solo a Ventas, alcanzaba para leer nómina o contabilidad, saltándose los
    # permisos que el ERP sí aplica en su propia interfaz.
    #
    # Es la opción A de `docs/seguridad/02-fase-1-datos-erp.md`: cierra el
    # agujero ya. La opción B (lista de tablas permitidas por módulo, para que
    # un usuario común conserve la consulta libre sobre lo suyo) queda para
    # cuando haya uso real que medir.
    if allowed_modules is None:
        tools.insert(
            2,
            _spec(
                "consultar_libre",
                _CONSULTAR_LIBRE_DESCRIPTION,
                CONSULTAR_LIBRE_SCHEMA,
                build_consultar_libre_impl(conversation_id, erp_database_id),
            ),
        )
    return tools
