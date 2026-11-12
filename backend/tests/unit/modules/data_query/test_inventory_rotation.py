"""Rotación de inventario: el cruce de existencias con ventas lo hace la base.

En la demo, el modelo cruzó dos muestras recortadas y dejó por fuera la MICHELIN
FORCE LTX. Con esta entidad es una sola consulta con criterio explícito.
"""

from __future__ import annotations

from app.modules.data_query.application.query_compiler import compile_query, widen_limit
from app.modules.data_query.application.query_parser import parse_semantic_query
from app.modules.data_query.infrastructure.catalog import get_entity


def _query() -> dict[str, object]:
    return {
        "entidad": "inventario_rotacion",
        "modo": "detalle",
        "campos": ["codigo", "producto", "existencia", "dias_sin_venta"],
        "filtros": [
            {"campo": "existencia", "op": ">", "valor": 0},
            {"campo": "dias_sin_venta", "op": ">=", "valor": 365},
        ],
        "orden": {"campo": "dias_sin_venta", "dir": "desc"},
    }


def test_slow_movers_are_one_complete_query_with_an_explicit_criterion() -> None:
    entity = get_entity("inventario_rotacion")
    assert entity is not None

    compiled = compile_query(parse_semantic_query(_query()), entity)

    # Nunca vendido cuenta desde la primera compra: no se pierde.
    assert "COALESCE(v.ultima_venta, c.primera_compra)" in compiled.sql
    assert 'p."tipo" = 0' in compiled.sql
    assert compiled.sql.rstrip().endswith(f"LIMIT {compiled.limit}")


def test_the_full_result_reads_more_rows_than_the_model_sees() -> None:
    entity = get_entity("inventario_rotacion")
    assert entity is not None
    compiled = compile_query(parse_semantic_query(_query()), entity)

    widened = widen_limit(compiled, 10_001)

    assert widened.sql.rstrip().endswith("LIMIT 10001")
    assert widened.params == compiled.params


def test_it_requires_the_inventory_module() -> None:
    entity = get_entity("inventario_rotacion")
    assert entity is not None
    assert not entity.allowed_for(frozenset({"VENTA"}))
    assert entity.allowed_for(frozenset({"INVENTARIO"}))
