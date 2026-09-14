"""Tools MCP que exponen el catálogo de conocimiento al LLM.

Cada tool recibe `allowed_modules` por clausura (set por turno desde el
usuario autenticado) y filtra antes de devolver al LLM. El catálogo se
inyecta también por clausura — es un singleton in-process cargado al
boot, sin I/O en la tool.

Notas de diseño:
- Las respuestas son diccionarios serializables JSON, sin objetos
  Pydantic crudos. El LLM consume strings.
- Si no hay matches o el módulo no está permitido, retornamos
  estructuras vacías con un `message` explicando el motivo en lenguaje
  natural. El LLM eso lo traduce al usuario.
- NUNCA exponemos detalles internos (paths de archivo, IDs de DB).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.knowledge.domain.entities import (
    FaqEntry,
    FormEntry,
    GlossaryEntry,
    ModuleEntry,
    WorkflowEntry,
)
from app.modules.knowledge.domain.interfaces import KnowledgeCatalog

# ──────────────────────────────────────────────────────────────────────
# Serializers — qué le mandamos al LLM por tool
# ──────────────────────────────────────────────────────────────────────


def _humanize_form_name(name: str) -> str:
    """Convierte 'frmConciliacionBancaria' en 'Conciliación bancaria'.

    Quita prefijo 'frm', separa por mayúsculas, capitaliza primera y
    pone tildes donde el ERP las usa (aproximación heurística para
    nombres sin user_label declarado).
    """
    s = name.removeprefix("frm")
    # Insertar espacios antes de mayúsculas internas:
    # "ConciliacionBancaria" → "Conciliacion Bancaria"
    out: list[str] = []
    for i, ch in enumerate(s):
        if i > 0 and ch.isupper():
            out.append(" ")
        out.append(ch)
    humanized = "".join(out)
    # Heurística simple: tildes comunes que el ERP usa
    replacements = {
        "Conciliacion": "Conciliación",
        "Nomina": "Nómina",
        "Liquidacion": "Liquidación",
        "Devolucion": "Devolución",
        "Generacion": "Generación",
        "Recalcular": "Recalcular",
        "Informacion": "Información",
        "Numeracion": "Numeración",
        "Configuracion": "Configuración",
        "Validacion": "Validación",
        "Aprobacion": "Aprobación",
        "Confirmacion": "Confirmación",
        "Notificacion": "Notificación",
        "Modificacion": "Modificación",
        "Eliminacion": "Eliminación",
        "Categoria": "Categoría",
        "Articulo": "Artículo",
        "Codigo": "Código",
        "Telefono": "Teléfono",
        "Direccion": "Dirección",
    }
    for src, dst in replacements.items():
        humanized = humanized.replace(src, dst)
    # Primera letra mayúscula, el resto como vino
    if humanized:
        humanized = humanized[0].upper() + humanized[1:]
    return humanized


def _form_to_payload(form: FormEntry) -> dict[str, Any]:
    """Vista compacta de un formulario para el LLM.

    Reglas:
    - NO incluimos `internal_name` — el LLM no debe ver el frmXxx.
    - `user_label` siempre presente y legible.
    - Campos vacíos se OMITEN para que el LLM no los lea como "sin info".
    """
    label = form.user_label or _humanize_form_name(form.name)
    payload: dict[str, Any] = {
        "nombre": label,
        "modulo": form.module.value,
        "tipo": form.type.value,
        "descripcion": form.description,
    }
    if form.navigation_path:
        payload["ruta_de_menu"] = " → ".join(form.navigation_path)
    if form.prerequisites:
        payload["requisitos_previos"] = form.prerequisites
    if form.how_to:
        payload["pasos"] = [
            {"paso": s.step, "accion": s.action, "detalle": s.detail}
            for s in form.how_to
        ]
    if form.actions:
        payload["acciones_disponibles"] = form.actions
    if form.filters:
        payload["filtros"] = form.filters
    if form.business_rules:
        payload["reglas_de_negocio"] = form.business_rules
    if form.calculations:
        payload["calculos"] = [
            {"nombre": c.name, "formula": c.formula, "explicacion": c.explanation}
            for c in form.calculations
        ]
    if form.outputs:
        payload["produce"] = form.outputs
    if form.common_issues:
        payload["problemas_frecuentes"] = [
            {"problema": ci.problem, "solucion": ci.solution} for ci in form.common_issues
        ]
    if form.related_forms:
        related = [_humanize_form_name(n) for n in form.related_forms]
        payload["procesos_relacionados"] = related
    return payload


def _form_summary(form: FormEntry) -> dict[str, Any]:
    """Vista compacta para listados."""
    return {
        "nombre": form.user_label or _humanize_form_name(form.name),
        "tipo": form.type.value,
        "descripcion": form.description,
    }


def _module_to_payload(module: ModuleEntry) -> dict[str, Any]:
    return {
        "code": module.code.value,
        "label": module.label,
        "purpose": module.purpose,
        "tags": module.tags,
        "main_forms": module.main_forms,
        "main_workflows": module.main_workflows,
    }


def _workflow_to_payload(wf: WorkflowEntry) -> dict[str, Any]:
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "modules": [m.value for m in wf.modules],
        "steps": [
            {
                "step": s.step,
                "form": s.form,
                "action": s.action,
                "optional": s.optional,
                "detail": s.detail,
            }
            for s in wf.steps
        ],
    }


def _faq_to_payload(faq: FaqEntry) -> dict[str, Any]:
    return {
        "id": faq.id,
        "question": faq.question,
        "answer_summary": faq.answer_summary,
        "related_forms": faq.related_forms,
        "related_workflows": faq.related_workflows,
        "module": faq.module.value if faq.module else None,
    }


def _glossary_to_payload(entry: GlossaryEntry) -> dict[str, Any]:
    return {
        "term": entry.term,
        "definition": entry.definition,
        "aliases": entry.aliases,
    }


# ──────────────────────────────────────────────────────────────────────
# Builders de implementación — clausuran catálogo + módulos permitidos
# ──────────────────────────────────────────────────────────────────────


def build_buscar_por_intencion_impl(
    catalog: KnowledgeCatalog,
    allowed_modules: frozenset[ModuleCode] | None,
) -> Callable[[dict[str, Any]], Any]:
    async def impl(args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("consulta", "")).strip()
        if not query:
            return {
                "matches": [],
                "message": "La consulta llegó vacía. Reformulá la búsqueda.",
            }
        hits = catalog.search_by_intent(query, allowed_modules=allowed_modules, limit=3)
        if not hits:
            return {
                "matches": [],
                "message": (
                    "No encontré un formulario o concepto del ERP que matchee "
                    "esa consulta dentro de los módulos disponibles para el usuario. "
                    "Sugerí preguntar de otra forma o aclarar el tema."
                ),
            }
        return {
            "matches": [{"score": h.score, "form": _form_to_payload(h.form)} for h in hits],
        }

    return impl


def build_describir_modulo_impl(
    catalog: KnowledgeCatalog,
    allowed_modules: frozenset[ModuleCode] | None,
) -> Callable[[dict[str, Any]], Any]:
    async def impl(args: dict[str, Any]) -> dict[str, Any]:
        code_raw = str(args.get("modulo", "")).strip().upper()
        try:
            code = ModuleCode(code_raw)
        except ValueError:
            return {
                "module": None,
                "message": f"Módulo desconocido: '{code_raw}'.",
            }
        mod = catalog.describe_module(code, allowed_modules=allowed_modules)
        if mod is None:
            return {
                "module": None,
                "message": (
                    f"El usuario no tiene acceso al módulo {code_raw} o el "
                    "módulo no está documentado en el catálogo."
                ),
            }
        forms = catalog.list_forms_by_module(code, allowed_modules=allowed_modules)
        return {
            "module": _module_to_payload(mod),
            "forms": [_form_summary(f) for f in forms[:20]],
        }

    return impl


def build_obtener_formulario_impl(
    catalog: KnowledgeCatalog,
    allowed_modules: frozenset[ModuleCode] | None,
) -> Callable[[dict[str, Any]], Any]:
    async def impl(args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("nombre", "")).strip()
        if not name:
            return {"form": None, "message": "Falta el nombre del formulario."}
        form = catalog.get_form(name, allowed_modules=allowed_modules)
        if form is None:
            return {
                "form": None,
                "message": (f"No encontré '{name}' o el usuario no tiene acceso a su módulo."),
            }
        return {"form": _form_to_payload(form)}

    return impl


def build_obtener_workflow_impl(
    catalog: KnowledgeCatalog,
    allowed_modules: frozenset[ModuleCode] | None,
) -> Callable[[dict[str, Any]], Any]:
    async def impl(args: dict[str, Any]) -> dict[str, Any]:
        wid = str(args.get("workflow_id", "")).strip()
        if not wid:
            return {"workflow": None, "message": "Falta el id del workflow."}
        wf = catalog.get_workflow(wid, allowed_modules=allowed_modules)
        if wf is None:
            return {
                "workflow": None,
                "message": f"Workflow '{wid}' no encontrado o sin acceso.",
            }
        return {"workflow": _workflow_to_payload(wf)}

    return impl


def build_responder_faq_impl(
    catalog: KnowledgeCatalog,
    allowed_modules: frozenset[ModuleCode] | None,
) -> Callable[[dict[str, Any]], Any]:
    async def impl(args: dict[str, Any]) -> dict[str, Any]:
        question = str(args.get("pregunta", "")).strip()
        if not question:
            return {"faqs": [], "message": "La pregunta llegó vacía."}
        faqs = catalog.answer_faq(question, allowed_modules=allowed_modules, limit=3)
        return {"faqs": [_faq_to_payload(f) for f in faqs]}

    return impl


def build_traducir_termino_impl(
    catalog: KnowledgeCatalog,
) -> Callable[[dict[str, Any]], Any]:
    async def impl(args: dict[str, Any]) -> dict[str, Any]:
        term = str(args.get("termino", "")).strip()
        if not term:
            return {"entry": None, "message": "Falta el término."}
        entry = catalog.translate_term(term)
        if entry is None:
            return {
                "entry": None,
                "message": f"'{term}' no está en el glosario.",
            }
        return {"entry": _glossary_to_payload(entry)}

    return impl


def build_listar_modulos_impl(
    catalog: KnowledgeCatalog,
    allowed_modules: frozenset[ModuleCode] | None,
) -> Callable[[dict[str, Any]], Any]:
    async def impl(_args: dict[str, Any]) -> dict[str, Any]:
        modules = catalog.list_modules(allowed_modules=allowed_modules)
        return {
            "modules": [
                {"code": m.code.value, "label": m.label, "purpose": m.purpose} for m in modules
            ],
        }

    return impl


# ──────────────────────────────────────────────────────────────────────
# Tool unificada — un único punto de entrada al catálogo
# ──────────────────────────────────────────────────────────────────────
#
# Por qué consolidamos: el Claude Agent SDK pasa a modo "deferred tools"
# cuando hay más de ~5-6 tools registradas, obligando al LLM a llamar
# `ToolSearch` antes de cualquier tool. Ese cambio de paradigma confunde
# al modelo: en lugar de usar resultados de tools que llamó, alucina
# que "el catálogo no responde" porque está procesando el ciclo
# discovery → call → result de forma más cautelosa.
#
# Solución: una única tool `consultar_conocimiento` que despacha
# internamente por `tipo`. El comportamiento del catálogo no cambia,
# solo la fachada hacia el LLM.

# Fuente única de los valores de `tipo`: la usan el dispatcher y el JSON
# Schema de la tool (`tools/schemas.py`).
KNOWLEDGE_TIPOS: tuple[str, ...] = (
    "intencion",
    "modulo",
    "workflow",
    "faq",
    "glosario",
    "modulos_disponibles",
    "formulario",
)


def build_consultar_conocimiento_impl(
    catalog: KnowledgeCatalog,
    allowed_modules: frozenset[ModuleCode] | None,
) -> Callable[[dict[str, Any]], Any]:
    """Constructor de la tool unificada del catálogo.

    Internamente delega a las implementaciones existentes según `tipo`.
    Mantenemos las funciones individuales porque los tests y el debug
    las usan por separado.
    """
    intencion = build_buscar_por_intencion_impl(catalog, allowed_modules)
    modulo = build_describir_modulo_impl(catalog, allowed_modules)
    workflow = build_obtener_workflow_impl(catalog, allowed_modules)
    faq = build_responder_faq_impl(catalog, allowed_modules)
    glosario = build_traducir_termino_impl(catalog)
    modulos = build_listar_modulos_impl(catalog, allowed_modules)
    formulario = build_obtener_formulario_impl(catalog, allowed_modules)

    async def impl(args: dict[str, Any]) -> dict[str, Any]:
        tipo = str(args.get("tipo", "intencion")).strip().lower()
        consulta = str(args.get("consulta", "")).strip()

        if tipo == "intencion":
            return await intencion({"consulta": consulta})
        if tipo == "modulo":
            return await modulo({"modulo": consulta})
        if tipo == "workflow":
            return await workflow({"workflow_id": consulta})
        if tipo == "faq":
            return await faq({"pregunta": consulta})
        if tipo == "glosario":
            return await glosario({"termino": consulta})
        if tipo == "modulos_disponibles":
            return await modulos({})
        if tipo == "formulario":
            return await formulario({"nombre": consulta})

        return {
            "error": (
                f"Tipo '{tipo}' no reconocido. Valores válidos: "
                f"{', '.join(KNOWLEDGE_TIPOS)}."
            ),
        }

    return impl
