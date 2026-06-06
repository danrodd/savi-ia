"""Diagnóstico del catálogo de conocimiento — usalo cuando el chat no
encuentra cosas que debería encontrar.

Recorre paso por paso:
1. ¿Existe el directorio data/?
2. ¿Cuántos archivos hay y se cargan todos?
3. ¿La búsqueda por intención encuentra resultados con queries típicas?
4. ¿Las tools (build_buscar_por_intencion_impl, etc.) devuelven lo
   correcto cuando se las llama directamente?

Uso:
    uv run python -m scripts.debug_knowledge

Salida: imprime un reporte con OK / FAIL en cada paso.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path


def section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print("=" * 70)


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def info(msg: str) -> None:
    print(f"     {msg}")


async def main() -> None:
    # ── Paso 1: el directorio existe ────────────────────────────────────
    section("Paso 1 — Directorio del catálogo")
    root = Path("app/modules/knowledge/data").resolve()
    if not root.exists():
        fail(f"NO existe: {root}")
        info("Esto significa que el bootstrap nunca corrió o el path es otro.")
        sys.exit(1)
    ok(f"Existe: {root}")

    forms_files = list(root.rglob("forms/*.json"))
    workflows_files = list(root.rglob("workflows/*.json"))
    faqs_files = list(root.rglob("faqs/*.json"))
    info(f"  forms     en disco: {len(forms_files)}")
    info(f"  workflows en disco: {len(workflows_files)}")
    info(f"  faqs      en disco: {len(faqs_files)}")

    target_form = root / "modules" / "contabilidad" / "forms" / "frmConciliacionBancaria.json"
    if target_form.exists():
        ok(f"Existe: {target_form.name}")
    else:
        fail(f"NO existe: {target_form}")
        info("Sin ese archivo, el catálogo no tiene frmConciliacionBancaria.")
        sys.exit(1)

    # ── Paso 2: el catálogo carga limpio ────────────────────────────────
    section("Paso 2 — Carga del catálogo")
    from app.modules.knowledge.infrastructure.static_catalog import (
        load_static_catalog,
    )

    try:
        catalog = load_static_catalog(root)
    except Exception as e:
        fail(f"Falló load_static_catalog: {type(e).__name__}: {e}")
        sys.exit(1)

    # Acceso interno solo para diagnóstico — no es API pública.
    forms_loaded = len(catalog._forms_by_name)  # type: ignore[attr-defined]
    modules_loaded = len(catalog._modules_by_code)  # type: ignore[attr-defined]
    wfs_loaded = len(catalog._workflows_by_id)  # type: ignore[attr-defined]
    faqs_loaded = len(catalog._faqs)  # type: ignore[attr-defined]
    ok(f"Catálogo cargado: {forms_loaded} forms, {modules_loaded} módulos, {wfs_loaded} workflows, {faqs_loaded} faqs")

    if "frmConciliacionBancaria" in catalog._forms_by_name:  # type: ignore[attr-defined]
        ok("frmConciliacionBancaria está en memoria")
        form = catalog._forms_by_name["frmConciliacionBancaria"]  # type: ignore[attr-defined]
        info(f"  module: {form.module.value}")
        info(f"  description: {form.description[:80]}…")
        info(f"  keywords: {form.keywords}")
    else:
        fail("frmConciliacionBancaria NO está en memoria")
        sys.exit(1)

    # ── Paso 3: búsqueda por intención (sin filtro de módulos = admin) ──
    section("Paso 3 — search_by_intent (admin / sin filtro)")
    queries = [
        "necesito conciliar el extracto del banco con la contabilidad",
        "conciliar banco",
        "cuadrar extracto bancario",
        "como facturo a un cliente",
        "ciclo de venta",
    ]
    for q in queries:
        hits = catalog.search_by_intent(q, allowed_modules=None, limit=3)
        if hits:
            top = hits[0]
            ok(f'"{q}" → {top.form.name} (score={top.score})')
        else:
            fail(f'"{q}" → SIN matches')

    # ── Paso 4: la TOOL real (la que ve el LLM) ─────────────────────────
    section("Paso 4 — Tool buscar_por_intencion (caso admin)")
    from app.modules.chat.infrastructure.llm.mcp.tools.knowledge import (
        build_buscar_por_intencion_impl,
    )

    impl_admin = build_buscar_por_intencion_impl(catalog, None)
    result = await impl_admin(
        {"consulta": "necesito conciliar el extracto del banco con la contabilidad"}
    )
    matches = result.get("matches", [])
    if matches:
        ok(f"La tool devuelve {len(matches)} match(es) para admin")
        top_form = matches[0]["form"]
        info(f"  Top match: {top_form['user_label']} ({top_form['module']})")
        info(f"  Score: {matches[0]['score']}")
        info(f"  Tiene navigation_path: {bool(top_form.get('navigation_path'))}")
        info(f"  Tiene how_to: {bool(top_form.get('how_to'))}")
    else:
        fail("La tool devuelve VACÍO para admin")
        info(f"  Mensaje devuelto al LLM: {result.get('message')}")

    # ── Paso 5: ver qué pasa con frozenset() vacío (sin permisos) ──────
    section("Paso 5 — Tool con allowed_modules vacío (regresión)")
    impl_no_perms = build_buscar_por_intencion_impl(catalog, frozenset())
    result_empty = await impl_no_perms(
        {"consulta": "necesito conciliar el extracto del banco"}
    )
    if not result_empty.get("matches"):
        ok("Con frozenset() vacío devuelve [] correctamente (esperado)")
        info(f"  Mensaje: {result_empty.get('message')}")
    else:
        warn("Con frozenset() vacío devolvió matches — esto NO debería pasar")

    # ── Paso 6: singleton — ¿está inicializado el provider? ─────────────
    section("Paso 6 — Singleton del catálogo")
    from app.modules.knowledge.infrastructure.catalog_provider import (
        get_catalog,
        init_catalog,
    )

    try:
        get_catalog()
        ok("Singleton ya estaba inicializado")
    except RuntimeError:
        warn("Singleton NO inicializado — esto es esperado porque este script no pasa por main.lifespan")
        init_catalog(root)
        ok("Inicializado manualmente desde el script — el lifespan del backend debería hacer lo mismo al boot")

    section("Diagnóstico completo")
    print("\nSi todos los pasos pasaron OK:")
    print("  → el catálogo, search y tool funcionan correctamente en aislamiento.")
    print("  → el problema está en el RUNTIME del backend:")
    print("     - ¿Está el backend corriendo el código nuevo? (¿reiniciaste?)")
    print("     - ¿lifespan se ejecutó? Buscá en logs algo tipo 'Application startup complete'.")
    print("     - ¿La tool está registrada en el MCP server del turno actual?")
    print()
    print("Si algún paso falló:")
    print("  → el reporte arriba te dice exactamente dónde.")


if __name__ == "__main__":
    asyncio.run(main())
