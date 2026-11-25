"""Las tablas del ERP que lee una consulta libre, para el reporte de vacíos."""

from __future__ import annotations

from app.modules.free_query.application.referenced_tables import MAX_TABLES, referenced_tables

# La consulta que armó el modelo el 2026-11-25 al pedir la retención en la fuente.
_REPORTE = """
WITH iva AS (
    SELECT "idFacturaCompra", SUM("subtotal") AS base_19
    FROM "CuentaPagar"."DetalleFacturaCompra" GROUP BY "idFacturaCompra"
), retefuente AS (
    SELECT fr."idFacturaCompra", SUM(fr."valorRetencion") AS r
    FROM "CuentaPagar"."FacturaIndicadorRetencionCompra" AS fr
    JOIN "Inventario"."IndicadorRetencion" AS ir
      ON ir."idIndicadorRetencion" = fr."idIndicadorRetencion"
    GROUP BY fr."idFacturaCompra"
)
SELECT fc."numero", iva.base_19, rf.r
FROM "CuentaPagar"."FacturaCompra" AS fc
JOIN "Tercero"."Tercero" AS t ON t."idTercero" = fc."idTercero"
LEFT JOIN iva ON iva."idFacturaCompra" = fc."idFacturaCompra"
LEFT JOIN retefuente AS rf ON rf."idFacturaCompra" = fc."idFacturaCompra"
WHERE fc."fecha" >= '2026-08-01'
"""


def test_it_lists_the_erp_tables_and_leaves_the_ctes_out() -> None:
    assert referenced_tables(_REPORTE) == [
        "CuentaPagar.DetalleFacturaCompra",
        "CuentaPagar.FacturaCompra",
        "CuentaPagar.FacturaIndicadorRetencionCompra",
        "Inventario.IndicadorRetencion",
        "Tercero.Tercero",
    ]


def test_schema_lookups_and_tables_without_schema_are_not_erp_tables() -> None:
    assert (
        referenced_tables(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'Factura'"
        )
        == []
    )
    assert referenced_tables("SELECT 1 FROM dual") == []


def test_nothing_from_the_query_values_leaks_into_the_names() -> None:
    sql = (
        'SELECT "razonSocial" FROM "Tercero"."Tercero" WHERE "numeroIdentificacion" = \'900042543\''
    )

    assert referenced_tables(sql) == ["Tercero.Tercero"]


def test_an_unreadable_query_gives_no_tables() -> None:
    assert referenced_tables("SELEC esto no es sql") == []


def test_the_list_is_capped() -> None:
    joins = " ".join(f'JOIN "S"."T{i}" t{i} ON TRUE' for i in range(MAX_TABLES + 5))

    assert len(referenced_tables(f'SELECT 1 FROM "S"."Base" b {joins}')) == MAX_TABLES
