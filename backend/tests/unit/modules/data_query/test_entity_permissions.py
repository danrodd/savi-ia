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
    """Ventas, terceros y cartera no cambian: las ve cualquier usuario."""
    assert {"ventas", "ventas_detalle", "terceros", "cartera"} <= _names(frozenset())


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
