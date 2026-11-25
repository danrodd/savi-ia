"""Arma el diccionario del ERP que usa SAVI y el paquete de validación (fase 5).

Dos salidas, desde el inventario (`inventory.py`) y el borrador (`draft.py`):

- `pack`: un Excel por módulo para el equipo del ERP. Cada fila es la tabla o una
  columna con la descripción propuesta; el equipo marca si es correcta o escribe la
  corrección. Corrigen, no escriben desde cero.
- `dictionary`: los JSON de `app/modules/knowledge/data/erp_dictionary/`, uno por
  módulo. Si se pasa la carpeta con los Excel devueltos, las correcciones mandan y
  lo revisado queda `validado`.

    uv run python -m scripts.erp_dictionary.build pack \\
        --inventory ../../savi-datos/diccionario-erp/inventory.json \\
        --draft ../../savi-datos/diccionario-erp/draft.json \\
        --out ../../savi-datos/diccionario-erp/validacion

    uv run python -m scripts.erp_dictionary.build dictionary \\
        --inventory ... --draft ... [--reviewed ../../savi-datos/diccionario-erp/validacion] \\
        --out app/modules/knowledge/data/erp_dictionary
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

MAX_REFERENCED_BY = 15
HEADERS = (
    "Tabla",
    "Columna",
    "Tipo",
    "Descripción propuesta",
    "¿Es correcta? (Sí / No)",
    "Corrección (si no es correcta)",
    "Dudas para confirmar",
)
_YES = {"si", "sí", "s", "yes", "x", "ok"}


@dataclass(frozen=True)
class Review:
    correct: bool
    correction: str


def _norm(text: object) -> str:
    return "" if text is None else str(text).strip()


def read_reviews(folder: Path) -> dict[tuple[str, str], Review]:
    """(tabla, columna) -> lo que respondió el equipo. Columna "" = la tabla."""
    reviews: dict[tuple[str, str], Review] = {}
    for path in sorted(folder.glob("*.xlsx")) if folder.exists() else []:
        sheet = load_workbook(path, read_only=True).active
        if sheet is None:
            continue
        for row in sheet.iter_rows(min_row=2, values_only=True):
            table, column = _norm(row[0]), _norm(row[1])
            answer, correction = _norm(row[4]).casefold(), _norm(row[5])
            if not table or not (answer or correction):
                continue
            reviews[(table, column)] = Review(answer in _YES, correction)
    return reviews


def _text(proposed: str, review: Review | None) -> tuple[str, bool]:
    """El texto final y si quedó revisado."""
    if review is None:
        return proposed, False
    if review.correction:
        return review.correction, True
    return proposed, review.correct


def build_dictionary(
    inventory: Mapping[str, Any],
    draft: Mapping[str, Any],
    reviews: Mapping[tuple[str, str], Review] | None = None,
) -> dict[str, dict[str, Any]]:
    """Módulo -> {tabla -> entrada}. Solo las tablas que tienen borrador."""
    reviews = reviews or {}
    modules: dict[str, dict[str, Any]] = {}
    for key, entry in sorted(draft.items()):
        table = inventory["tables"].get(key)
        if table is None:
            continue
        description, table_ok = _text(entry.get("descripcion", ""), reviews.get((key, "")))
        columns: dict[str, dict[str, str]] = {}
        all_ok = table_ok
        for col in table["columns"]:
            proposed = entry.get("columnas", {}).get(col["name"], "")
            text, ok = _text(proposed, reviews.get((key, col["name"])))
            all_ok = all_ok and ok
            columns[col["name"]] = {"tipo": col["type"], "descripcion": text}
        modules.setdefault(table["module"], {})[key] = {
            "descripcion": description,
            "validado": all_ok,
            "clave_primaria": table.get("primary_key", []),
            "columnas": columns,
            "apunta_a": [
                f"{', '.join(fk['columns'])} -> {fk['references']}({', '.join(fk['ref_columns'])})"
                for fk in table.get("foreign_keys", [])
            ],
            "la_referencian": table.get("referenced_by", [])[:MAX_REFERENCED_BY],
        }
    return modules


def build_pack(inventory: Mapping[str, Any], draft: Mapping[str, Any], out: Path) -> list[Path]:
    """Un Excel por módulo, listo para que el equipo del ERP lo corrija."""
    out.mkdir(parents=True, exist_ok=True)
    by_module: dict[str, list[str]] = {}
    for key in sorted(draft):
        table = inventory["tables"].get(key)
        if table is not None:
            by_module.setdefault(table["module"], []).append(key)
    written: list[Path] = []
    header_fill = PatternFill("solid", fgColor="1F3A5F")
    table_fill = PatternFill("solid", fgColor="E8EEF6")
    for module, keys in sorted(by_module.items()):
        book = Workbook()
        sheet = book.active
        assert sheet is not None  # noqa: S101 — un libro nuevo siempre trae una hoja
        sheet.title = module[:31]
        sheet.append(HEADERS)
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        answer = DataValidation(type="list", formula1='"Sí,No"', allow_blank=True)
        sheet.add_data_validation(answer)
        for key in keys:
            entry, table = draft[key], inventory["tables"][key]
            sheet.append([key, "", "", entry.get("descripcion", ""), "", "", ""])
            row = sheet.max_row
            for cell in sheet[row]:
                cell.fill = table_fill
                cell.font = Font(bold=True)
            sheet.cell(row=row, column=7, value="\n".join(entry.get("dudas", [])))
            answer.add(f"E{row}")
            for col in table["columns"]:
                sheet.append(
                    [
                        key,
                        col["name"],
                        col["type"],
                        entry.get("columnas", {}).get(col["name"], ""),
                        "",
                        "",
                        "",
                    ]
                )
                answer.add(f"E{sheet.max_row}")
        for column, width in zip("ABCDEFG", (34, 26, 14, 70, 14, 50, 50), strict=True):
            sheet.column_dimensions[column].width = width
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.freeze_panes = "A2"
        path = out / f"{module}.xlsx"
        book.save(path)
        written.append(path)
    return written


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("what", choices=("pack", "dictionary"))
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--reviewed", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    inv, drf = _load(args.inventory), _load(args.draft)
    if args.what == "pack":
        files = build_pack(inv, drf, args.out)
        print(f"{len(files)} archivos en {args.out}")
    else:
        reviews = read_reviews(args.reviewed) if args.reviewed else {}
        modules = build_dictionary(inv, drf, reviews)
        args.out.mkdir(parents=True, exist_ok=True)
        for module, tables in modules.items():
            (args.out / f"{module}.json").write_text(
                json.dumps(tables, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
            )
        total = sum(len(t) for t in modules.values())
        validated = sum(1 for t in modules.values() for e in t.values() if e["validado"])
        print(f"{total} tablas en {len(modules)} módulos ({validated} validadas) -> {args.out}")
