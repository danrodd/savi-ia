"""Bootstrap del catálogo de conocimiento desde `sisfec_knowledge_base_v2.json`.

Uso (one-shot):

    uv run python -m scripts.bootstrap_knowledge \\
        --source "C:/Users/hikig/Documents/SEOGroup/Conocimiento/sisfec_knowledge_base_v2.json" \\
        --target app/modules/knowledge/data

Lee el JSON v2 y emite la estructura de archivos por entidad:

    target/
    ├── modules/
    │   ├── contabilidad/
    │   │   ├── overview.json
    │   │   ├── forms/<frmXxx>.json
    │   │   ├── workflows/<wf_id>.json
    │   │   └── faqs/<faq_id>.json
    │   └── ...
    └── shared/
        └── glossary.json   (siempre como lista, vacío por ahora)

- Idempotente: re-correrlo regenera los archivos. Si después editás
  manualmente un form, el siguiente bootstrap lo pisaría — por eso es
  ONE-SHOT, no se corre en CI.
- Mapea los nombres de módulos del v2 (mixedCase) a `ModuleCode` (UPPER
  con tildes donde corresponda).
- Si el v2 trae módulos sin equivalente en SAVI (Inicio, Herramientas),
  los SALTA con warning — esos no son módulos del ERP de negocio, son
  utilidades.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Mapeo nombre del v2 → ModuleCode de SAVI (string value para evitar
# importar el enum y pelearse con el path al correr el script suelto).
_V2_MODULE_TO_CODE: dict[str, str] = {
    "Inventario": "INVENTARIO",
    "CuentaCobrar": "CUENTACOBRAR",
    "CuentaPagar": "CUENTAPAGAR",
    "Cartera": "CARTERAFINANCIERA",
    "Contabilidad": "CONTABILIDAD",
    "Nomina": "NÓMINA",
    "Venta": "VENTA",
    "Tercero": "TERCERO",
    "ActivoFijo": "ACTIVOFIJO",
    "Herramientas": "HERRAMIENTA",
    # Inicio y Seguridad NO se mapean — Inicio es UI shell, Seguridad
    # ya está cubierto por el módulo de auth de SAVI.
}

# Slug del directorio (en disco) por código de módulo. Lowercase ascii.
_CODE_TO_SLUG: dict[str, str] = {
    "INVENTARIO": "inventario",
    "CUENTACOBRAR": "cuentacobrar",
    "CUENTAPAGAR": "cuentapagar",
    "CARTERAFINANCIERA": "carterafinanciera",
    "CONTABILIDAD": "contabilidad",
    "NÓMINA": "nomina",
    "VENTA": "venta",
    "TERCERO": "tercero",
    "ACTIVOFIJO": "activofijo",
    "HERRAMIENTA": "herramienta",
    "SEGURIDAD": "seguridad",
    "EMPRESA": "empresa",
    "GENERAL": "general",
    "BÚSQUEDA": "busqueda",
    "MANTENIMIENTO": "mantenimiento",
    "CULTIVO": "cultivo",
}


def _slug(name: str) -> str:
    """Convierte un identificador interno (frmXxx, wf_xxx) a slug-safe."""
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, data: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _build_form_entry(form: dict, module_code: str) -> dict:
    """Adapta el formato del v2 al schema de FormEntry."""
    entry: dict[str, Any] = {
        "name": form["name"],
        "module": module_code,
        "type": form["type"],
        "description": form.get("description", ""),
    }
    if (kw := form.get("keywords")) is not None:
        entry["keywords"] = list(kw)
    if (actions := form.get("actions")) is not None:
        entry["actions"] = list(actions)
    if (filters := form.get("filters")) is not None:
        entry["filters"] = list(filters)
    if (rules := form.get("business_rules")) is not None:
        entry["business_rules"] = list(rules)
    if (tables := form.get("db_tables")) is not None:
        entry["db_tables"] = list(tables)
    entry["source"] = "sisfec_knowledge_base v2"
    return entry


def _build_module_overview(module: dict, code: str) -> dict:
    forms = module.get("forms", [])
    main_forms = [f["name"] for f in forms[:4]]  # primeros 4 como representativos
    return {
        "code": code,
        "label": module.get("name", code.title()),
        "purpose": f"Módulo {module.get('name', code)} del ERP. Cubre {len(forms)} formularios.",
        "tags": list(module.get("tags", [])),
        "main_workflows": [],
        "main_forms": main_forms,
    }


def _build_workflow_entry(wf: dict, modules: list[str]) -> dict:
    return {
        "id": wf["id"],
        "name": wf["name"],
        "description": wf.get("description", wf["name"]),
        "modules": modules,
        "synonyms": [],
        "steps": [
            {
                "step": s["step"],
                "form": s.get("form", "unknown"),
                "action": s["action"],
                "optional": s.get("optional", False),
            }
            for s in wf.get("steps", [])
        ],
    }


def _build_faq_entry(entry: dict, idx: int) -> dict:
    fid = f"faq_{idx:03d}"
    module_v2 = entry.get("module")
    module_code = _V2_MODULE_TO_CODE.get(module_v2) if module_v2 else None
    return {
        "id": fid,
        "question": entry["question"],
        "synonyms": [],
        "module": module_code,
        "answer_summary": entry.get("answer", ""),
        "related_forms": list(entry.get("forms", [])),
        "related_workflows": [],
    }


def _module_of_workflow(wf: dict) -> str | None:
    """Infiere el módulo principal de un workflow mirando el módulo del
    primer step. Si no se puede inferir, devuelve None y va a `shared/`."""
    steps = wf.get("steps", [])
    for s in steps:
        m = s.get("module")
        if m and m in _V2_MODULE_TO_CODE:
            return _V2_MODULE_TO_CODE[m]
    return None


def bootstrap(source: Path, target: Path) -> dict[str, int]:
    raw = json.loads(source.read_text(encoding="utf-8"))
    counts = {
        "modules": 0, "forms": 0, "workflows": 0, "faqs": 0,
        "skipped_modules": 0, "skipped_workflows": 0,
    }

    # Módulos + formularios
    for module in raw.get("modules", []):
        v2_name = module.get("name", "")
        code = _V2_MODULE_TO_CODE.get(v2_name)
        if code is None:
            print(f"[skip] Módulo no mapeado: {v2_name}", file=sys.stderr)
            counts["skipped_modules"] += 1
            continue
        slug = _CODE_TO_SLUG[code]
        dossier = target / "modules" / slug

        # overview.json
        _write_json(dossier / "overview.json", _build_module_overview(module, code))
        counts["modules"] += 1

        # forms/
        for form in module.get("forms", []):
            entry = _build_form_entry(form, code)
            _write_json(dossier / "forms" / f"{_slug(form['name'])}.json", entry)
            counts["forms"] += 1

    # Workflows: van bajo el módulo principal inferido del primer step.
    for wf in raw.get("business_workflows", []):
        primary = _module_of_workflow(wf)
        if primary is None:
            print(f"[skip] Workflow sin módulo claro: {wf.get('id')}", file=sys.stderr)
            counts["skipped_workflows"] += 1
            continue
        # Recolecta TODOS los módulos involucrados.
        involved: set[str] = set()
        for s in wf.get("steps", []):
            m = s.get("module")
            if m and m in _V2_MODULE_TO_CODE:
                involved.add(_V2_MODULE_TO_CODE[m])
        slug = _CODE_TO_SLUG[primary]
        wf_entry = _build_workflow_entry(wf, sorted(involved))
        _write_json(
            target / "modules" / slug / "workflows" / f"{_slug(wf['id'])}.json",
            wf_entry,
        )
        counts["workflows"] += 1

    # FAQs: van bajo el módulo declarado en el FAQ; si no, en general/.
    faq_root = target / "modules"
    for i, faq in enumerate(raw.get("question_to_form_map", {}).get("entries", []), 1):
        entry = _build_faq_entry(faq, i)
        module = entry.get("module")
        if module is not None:
            slug = _CODE_TO_SLUG[module]
            path = faq_root / slug / "faqs" / f"{entry['id']}.json"
        else:
            path = target / "shared" / "faqs" / f"{entry['id']}.json"
        _write_json(path, entry)
        counts["faqs"] += 1

    # Glossary: el v2 no trae uno, dejamos archivo vacío para que
    # exista el path.
    glossary_path = target / "shared" / "glossary.json"
    if not glossary_path.exists():
        _write_json(glossary_path, [])

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap knowledge catalog from v2 JSON.")
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Ruta al sisfec_knowledge_base_v2.json",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("app/modules/knowledge/data"),
        help="Carpeta destino. Default: app/modules/knowledge/data",
    )
    args = parser.parse_args()

    counts = bootstrap(args.source, args.target)
    print(json.dumps(counts, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
