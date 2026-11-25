"""Del borrador al diccionario: el equipo del ERP corrige y lo revisado queda validado."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from scripts.erp_dictionary.build import build_dictionary, build_pack, read_reviews

_INVENTORY = {
    "bases": 4,
    "tables": {
        "Contabilidad.PlanContable": {
            "module": "Contabilidad",
            "primary_key": ["idPlanContable"],
            "columns": [
                {"name": "codigo", "type": "character varying"},
                {"name": "naturaleza", "type": "boolean"},
            ],
            "foreign_keys": [],
            "referenced_by": [],
        }
    },
}
_DRAFT = {
    "Contabilidad.PlanContable": {
        "descripcion": "Plan de cuentas.",
        "columnas": {"codigo": "Código de la cuenta.", "naturaleza": "Posiblemente el tipo."},
        "dudas": ["¿true es débito?"],
        "validado": False,
    }
}


def test_without_review_everything_is_a_draft() -> None:
    modules = build_dictionary(_INVENTORY, _DRAFT)

    entry = modules["Contabilidad"]["Contabilidad.PlanContable"]
    assert entry["validado"] is False
    assert entry["columnas"]["naturaleza"] == {
        "tipo": "boolean",
        "descripcion": "Posiblemente el tipo.",
    }


def test_the_pack_round_trips_the_teams_corrections(tmp_path: Path) -> None:
    (path,) = build_pack(_INVENTORY, _DRAFT, tmp_path)
    book = load_workbook(path)
    sheet = book.active
    assert sheet is not None
    rows = list(sheet.iter_rows(min_row=2))
    assert rows[0][6].value == "¿true es débito?"  # las dudas van en la fila de la tabla
    # El equipo aprueba la tabla y el código, y corrige la naturaleza.
    for row in rows:
        column = row[1].value or ""
        if column == "naturaleza":
            row[4].value = "No"
            row[5].value = "true = débito (activos, gastos, costos); false = crédito."
        else:
            row[4].value = "Sí"
    book.save(path)

    entry = build_dictionary(_INVENTORY, _DRAFT, read_reviews(tmp_path))["Contabilidad"][
        "Contabilidad.PlanContable"
    ]

    assert entry["validado"] is True
    assert entry["columnas"]["naturaleza"]["descripcion"].startswith("true = débito")
    assert entry["columnas"]["codigo"]["descripcion"] == "Código de la cuenta."


def test_a_partly_reviewed_table_stays_a_draft(tmp_path: Path) -> None:
    (path,) = build_pack(_INVENTORY, _DRAFT, tmp_path)
    book = load_workbook(path)
    sheet = book.active
    assert sheet is not None
    next(sheet.iter_rows(min_row=2))[4].value = "Sí"  # solo la tabla
    book.save(path)

    entry = build_dictionary(_INVENTORY, _DRAFT, read_reviews(tmp_path))["Contabilidad"][
        "Contabilidad.PlanContable"
    ]

    assert entry["validado"] is False
