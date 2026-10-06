"""Cada entidad respeta los módulos del ERP del usuario."""

from __future__ import annotations

import pytest

from app.modules.chat.infrastructure.llm.tools.consultar_datos import build_description
from app.modules.data_query.application.run_semantic_query import run_semantic_query
from app.modules.data_query.infrastructure.catalog import get_entity, list_entities


def _names(modules: frozenset[str] | None) -> set[str]:
    return {entity.name for entity in list_entities(modules)}


def test_an_admin_sees_every_entity() -> None:
    assert {"inventario", "compras", "compras_detalle", "ventas"} <= _names(None)


def test_inventory_needs_the_inventory_module() -> None:
    assert "inventario" in _names(frozenset({"INVENTARIO"}))
    assert "inventario" not in _names(frozenset({"CUENTACOBRAR"}))


def test_purchases_need_accounts_payable() -> None:
    assert {"compras", "compras_detalle"} <= _names(frozenset({"CUENTAPAGAR"}))
    assert not {"compras", "compras_detalle"} & _names(frozenset({"INVENTARIO"}))


def test_entities_without_requirements_stay_open() -> None:
    """Ventas y terceros no cambian: las ve cualquier usuario."""
    assert {"ventas", "ventas_detalle", "terceros"} <= _names(frozenset())


def test_the_tool_description_hides_what_the_user_cannot_query() -> None:
    description = build_description(frozenset({"CUENTACOBRAR"}))

    assert "## ventas" in description
    assert "## inventario" not in description and "## compras" not in description


@pytest.mark.asyncio
async def test_asking_for_a_hidden_entity_is_refused_without_touching_the_erp() -> None:
    answer = await run_semantic_query(
        {"entidad": "inventario", "modo": "agregado", "metricas": ["unidades"]},
        modules=frozenset({"CUENTACOBRAR"}),
    )

    assert "no tiene acceso" in answer and "INVENTARIO" in answer


def test_required_modules_are_real_erp_modules() -> None:
    from app.modules.auth.domain.value_objects.module_code import ModuleCode

    valid = {module.value for module in ModuleCode}
    for entity in list_entities():
        assert set(entity.required_modules) <= valid, entity.name
    assert get_entity("inventario") is not None


# ── Búsqueda por nombre sin coincidencias ────────────────────────────────


def test_a_long_name_search_without_results_suggests_fewer_words() -> None:
    from app.modules.data_query.application.run_semantic_query import _narrower_search_hint
    from app.modules.data_query.domain.semantic_query import FilterOp, QueryFilter

    hint = _narrower_search_hint(
        [QueryFilter("producto", FilterOp.CONTAINS, "acetaminofén 500 mg de 10 tabletas (B)")]
    )

    assert hint is not None and "'acetaminofen 500'" in hint


def test_a_short_search_without_results_is_just_empty() -> None:
    from app.modules.data_query.application.run_semantic_query import _narrower_search_hint
    from app.modules.data_query.domain.semantic_query import FilterOp, QueryFilter

    assert _narrower_search_hint([QueryFilter("producto", FilterOp.CONTAINS, "tornillo")]) is None


# ── Cartera separada por lado ────────────────────────────────────────────


def _cartera():
    entity = get_entity("cartera")
    assert entity is not None
    return entity


def test_receivables_only_add_the_client_side_as_a_fixed_filter() -> None:
    scoped = _cartera().scoped_for(frozenset({"CUENTACOBRAR"}))

    assert 'ft."tipoDocumento" IN (2, 14)' in scoped.base_filters[-1]
    assert "(3, 7, 9, 13, 15)" not in scoped.base_filters[-1]


def test_payables_only_add_the_supplier_side() -> None:
    scoped = _cartera().scoped_for(frozenset({"CUENTAPAGAR"}))

    assert "(3, 7, 9, 13, 15)" in scoped.base_filters[-1]
    assert "(2, 14)" not in scoped.base_filters[-1]


def test_both_modules_see_both_sides_and_an_admin_sees_everything() -> None:
    both = _cartera().scoped_for(frozenset({"CUENTACOBRAR", "CUENTAPAGAR"}))

    assert " OR " in both.base_filters[-1]
    assert _cartera().scoped_for(None) is _cartera()


def test_without_either_module_cartera_is_hidden() -> None:
    assert "cartera" not in _names(frozenset({"INVENTARIO"}))
    assert "cartera" in _names(frozenset({"VENTA"}))


def test_the_description_says_which_side_the_user_can_see() -> None:
    description = build_description(frozenset({"VENTA"}))

    assert "solo puede ver lo que deben los clientes" in description


@pytest.mark.asyncio
async def test_asking_for_cartera_without_its_modules_names_them() -> None:
    answer = await run_semantic_query(
        {"entidad": "cartera", "modo": "agregado", "metricas": ["saldo"]},
        modules=frozenset({"INVENTARIO"}),
    )

    assert "CUENTACOBRAR" in answer and "CUENTAPAGAR" in answer


# ── Total que suma varias coincidencias de una búsqueda ──────────────────


def _fake_executor(rows_by_grouping: dict[bool, list[dict[str, object]]]):
    """Devuelve filas distintas para la consulta principal (sin GROUP BY) y
    para la verificación agrupada por el campo buscado."""
    from app.modules.data_query.domain.query_result import QueryResult

    async def execute(compiled, entidad, modo, *, erp_database_id=None):  # noqa: ANN001, ANN202, ARG001
        rows = rows_by_grouping["GROUP BY" in compiled.sql]
        return QueryResult(
            entidad=entidad,
            modo=modo,
            columns=list(rows[0]) if rows else [],
            rows=rows,
            row_count=len(rows),
        )

    return execute


_TORNILLO_QUERY = {
    "entidad": "inventario",
    "modo": "agregado",
    "metricas": ["unidades"],
    "filtros": [{"campo": "producto", "op": "contiene", "valor": "tornillo MAD 6 2"}],
}


async def test_a_total_over_several_matching_products_warns_and_names_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.data_query.application.run_semantic_query as module

    monkeypatch.setattr(
        module,
        "execute_compiled",
        _fake_executor(
            {
                False: [{"unidades": 27115}],
                True: [
                    {"producto": 'TORNILLO MAD 6 * 2"', "unidades": 18183},
                    {"producto": 'TORNILLO MAD 6 * 1 1/2"', "unidades": 10700},
                ],
            }
        ),
    )

    answer = await run_semantic_query(_TORNILLO_QUERY)

    assert "27115" in answer
    assert "SUMA" in answer and 'TORNILLO MAD 6 * 2"' in answer
    assert "'producto' en 'dimensiones'" in answer


async def test_a_total_over_a_single_matching_product_has_no_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.data_query.application.run_semantic_query as module

    monkeypatch.setattr(
        module,
        "execute_compiled",
        _fake_executor(
            {
                False: [{"unidades": 18183}],
                True: [{"producto": 'TORNILLO MAD 6 * 2"', "unidades": 18183}],
            }
        ),
    )

    answer = await run_semantic_query(_TORNILLO_QUERY)

    assert "18183" in answer and "SUMA" not in answer


async def test_a_total_grouped_by_branch_still_warns_about_mixed_products(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.data_query.application.run_semantic_query as module

    def is_probe(sql: str) -> bool:
        return 'AS "producto"' in sql

    async def execute(compiled, entidad, modo, *, erp_database_id=None):  # noqa: ANN001, ANN202, ARG001
        from app.modules.data_query.domain.query_result import QueryResult

        rows: list[dict[str, object]] = (
            [{"producto": 'TORNILLO MAD 6 * 2"'}, {"producto": 'TORNILLO MAD 6 * 1 1/2"'}]
            if is_probe(compiled.sql)
            else [{"sucursal": "BODEGA", "unidades": 28883}]
        )
        return QueryResult(entidad, modo, list(rows[0]), rows, row_count=len(rows))

    monkeypatch.setattr(module, "execute_compiled", execute)

    answer = await run_semantic_query({**_TORNILLO_QUERY, "dimensiones": ["sucursal"]})

    assert "SUMA" in answer and 'TORNILLO MAD 6 * 1 1/2"' in answer


async def test_a_grouped_total_is_not_verified_again(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.data_query.application.run_semantic_query as module

    calls: list[str] = []
    rows = [{"producto": "A", "unidades": 1}, {"producto": "B", "unidades": 2}]

    async def execute(compiled, entidad, modo, *, erp_database_id=None):  # noqa: ANN001, ANN202, ARG001
        calls.append(compiled.sql)
        return await _fake_executor({True: rows, False: rows})(compiled, entidad, modo)

    monkeypatch.setattr(module, "execute_compiled", execute)

    answer = await run_semantic_query({**_TORNILLO_QUERY, "dimensiones": ["producto"]})

    assert len(calls) == 1 and "SUMA" not in answer
