"""Inventario del diccionario del ERP: la parte que une las bases, sin nombrarlas."""

from __future__ import annotations

from typing import Any

from scripts.erp_dictionary.inventory import Snapshot, functions_touching, merge, to_json


def _snapshot(*, with_saldo: bool, rows: int, fn_source: str = "") -> Snapshot:
    cols: list[dict[str, Any]] = [
        {
            "table_schema": "Contabilidad",
            "table_name": "Anticipo",
            "column_name": "idAnticipo",
            "data_type": "integer",
            "is_nullable": "NO",
        },
        {
            "table_schema": "Tercero",
            "table_name": "Tercero",
            "column_name": "idTercero",
            "data_type": "integer",
            "is_nullable": "NO",
        },
    ]
    if with_saldo:
        cols.append(
            {
                "table_schema": "Contabilidad",
                "table_name": "Anticipo",
                "column_name": "saldoAnticipo",
                "data_type": "numeric",
                "is_nullable": "YES",
            }
        )
    return Snapshot(
        columns=cols,
        comments={},
        column_comments={("Contabilidad.Anticipo", "saldoAnticipo"): "Lo que falta cruzar"},
        primary_keys={"Contabilidad.Anticipo": ["idAnticipo"]},
        foreign_keys=[
            {
                "schema": "Contabilidad",
                "table": "Anticipo",
                "columns": ["idTercero"],
                "ref_schema": "Tercero",
                "ref_table": "Tercero",
                "ref_columns": ["idTercero"],
            }
        ],
        rows={"Contabilidad.Anticipo": rows, "Tercero.Tercero": 10},
        functions={"Cartera.fnCruzarAnticipo": fn_source},
    )


def test_two_bases_merge_into_one_entry_per_table_without_naming_them() -> None:
    tables = merge(
        [
            _snapshot(with_saldo=True, rows=120, fn_source='UPDATE "Contabilidad"."Anticipo"'),
            _snapshot(with_saldo=False, rows=0),
        ]
    )
    out = to_json(tables, bases=2)
    anticipo = out["tables"]["Contabilidad.Anticipo"]

    assert out["bases"] == 2
    assert anticipo["usage"] == {"present_in": 2, "with_data": 1, "max_rows": 120}
    assert anticipo["primary_key"] == ["idAnticipo"]
    assert anticipo["foreign_keys"] == [
        {"columns": ["idTercero"], "references": "Tercero.Tercero", "ref_columns": ["idTercero"]}
    ]
    assert out["tables"]["Tercero.Tercero"]["referenced_by"] == ["Contabilidad.Anticipo(idTercero)"]
    saldo = next(c for c in anticipo["columns"] if c["name"] == "saldoAnticipo")
    assert saldo["present_in"] == 1  # una de las dos bases no la tiene (otra versión)
    assert saldo["comment"] == "Lo que falta cruzar"
    assert anticipo["functions"] == ["Cartera.fnCruzarAnticipo"]


def test_a_function_touches_a_table_only_with_its_schema_and_whole_name() -> None:
    functions = {
        "a.quoted": 'SELECT * FROM "Contabilidad"."Anticipo" WHERE x',
        "b.plain": "select * from contabilidad.anticipo",
        "c.other_schema": 'SELECT * FROM "Cartera"."Anticipo"',
        "d.longer_name": 'SELECT * FROM "Contabilidad"."AnticipoDetalle"',
    }

    assert functions_touching("Contabilidad.Anticipo", functions) == {"a.quoted", "b.plain"}
