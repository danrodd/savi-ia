"""Tool MCP `consultar_datos` — consulta semántica de la BD del ERP.

El LLM NO escribe SQL: arma un objeto de consulta (entidad + modo +
métricas/dimensiones/campos/filtros) que un compilador determinístico
traduce a SQL parametrizado. Ver docs/DB_ACCESS_DESIGN.md.

La descripción de la tool se genera desde el catálogo semántico para que
el LLM sepa exactamente qué entidades y campos puede pedir, sin
desincronizarse del modelo.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any, cast
from uuid import UUID

from app.modules.data_query.application.run_semantic_query import run_semantic_query
from app.modules.data_query.infrastructure.catalog import list_entities


def build_description(modules: Collection[str] | None = None) -> str:
    """Genera la descripción de la tool desde el catálogo vigente.

    Solo lista las entidades que el usuario puede consultar: si el modelo ni
    las ve, no promete datos que después le serían negados.
    """
    lines: list[str] = [
        "Consulta datos del ERP del cliente. NO escribís SQL: armás un "
        "objeto de consulta y el sistema lo traduce de forma segura.",
        "",
        "El argumento `consulta` es un objeto con esta forma:",
        "{",
        '  "entidad": "<nombre>",',
        '  "modo": "agregado" | "detalle" | "registro",',
        '  "metricas": ["..."],      // solo modo agregado',
        '  "dimensiones": ["..."],   // agrupar por (modo agregado)',
        '  "campos": ["..."],        // columnas (modo detalle/registro)',
        '  "filtros": [{"campo": "...", "op": "=", "valor": ...}],',
        '  "orden": {"campo": "...", "dir": "desc"},',
        '  "limite": 20',
        "}",
        "",
        "Operadores de filtro: =, !=, >, >=, <, <=, entre (valor=[a,b]), "
        "contiene (texto), en (valor=[...]).",
        "",
        "Modos:",
        "- agregado: métricas agrupadas por dimensiones (totales, conteos).",
        "- detalle: lista de filas (máx ~30). Para 'las últimas N facturas'.",
        "- registro: un único registro identificado por su clave.",
        "",
        "Reglas: no podés pedir listados masivos crudos; para muchos datos "
        "usá agregados. Para buscar un cliente por nombre usá entidad "
        "'terceros', modo 'detalle', filtro {campo:'nombre', op:'contiene', "
        "valor:'<texto>'} y obtené su 'id', luego filtrá ventas por "
        "{campo:'cliente_id', op:'=', valor:<id>}.",
        "",
        "=== Entidades disponibles ===",
    ]

    for ent in list_entities(modules):
        lines.append(f"\n## {ent.name}")
        if ent.description:
            lines.append(ent.description)
        visible = ent.visible_scopes(modules)
        if modules is not None and ent.row_scopes and len(visible) < len(ent.row_scopes):
            # Sin esto el modelo pedía "el lado proveedores", recibía vacío y
            # contestaba que no había deudas, cuando lo que no hay es permiso.
            labels = " y ".join(s.label for s in visible)
            lines.append(
                f"PERMISOS: este usuario solo puede ver {labels}. Si pregunta por "
                "el resto, decile que no tiene acceso a esa información en el ERP."
            )
        if ent.metrics:
            metricas = ", ".join(f"{m.name} ({m.label})" for m in ent.metrics.values())
            lines.append(f"- métricas: {metricas}")
        if ent.dimensions:
            dims = ", ".join(f"{d.name} ({d.label})" for d in ent.dimensions.values())
            lines.append(f"- dimensiones: {dims}")
        if ent.fields:
            campos = ", ".join(f"{c.name} ({c.label})" for c in ent.fields.values())
            lines.append(f"- campos (detalle/registro): {campos}")
        if ent.filters:
            filtros = ", ".join(ent.filters)
            lines.append(f"- filtros: {filtros}")

    return "\n".join(lines)


async def consultar_datos_impl(
    args: dict[str, Any],
    *,
    erp_database_id: UUID | None = None,
    modules: Collection[str] | None = None,
) -> dict[str, Any]:
    consulta = args.get("consulta")
    if not isinstance(consulta, dict):
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "El argumento 'consulta' debe ser un objeto con la forma "
                        "{entidad, modo, ...}."
                    ),
                }
            ],
            "isError": True,
        }
    text = await run_semantic_query(
        cast(dict[str, Any], consulta), erp_database_id=erp_database_id, modules=modules
    )
    return {"content": [{"type": "text", "text": text}]}
