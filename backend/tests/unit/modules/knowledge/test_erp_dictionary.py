"""Diccionario del ERP: el modelo lo consulta antes de escribir SQL libre."""

from __future__ import annotations

import json
from pathlib import Path

from app.modules.knowledge.infrastructure.erp_dictionary import load_dictionary

_COMPRAS = {
    "CuentaPagar.FacturaIndicadorRetencionCompra": {
        "descripcion": "Retenciones aplicadas a cada factura de compra.",
        "validado": False,
        "clave_primaria": ["idFacturaIndicadorRetencionCompra"],
        "columnas": {
            "valorRetencion": {"tipo": "numeric", "descripcion": "Valor retenido."},
            "idIndicadorRetencion": {"tipo": "integer", "descripcion": "Tipo de retención."},
        },
        "apunta_a": ["idFacturaCompra -> CuentaPagar.FacturaCompra(idFacturaCompra)"],
        "la_referencian": [],
    },
    "CuentaPagar.FacturaCompra": {
        "descripcion": "Cabecera de las facturas de compra a proveedores.",
        "validado": True,
        "columnas": {"valorImpuestosRetencion": {"tipo": "numeric", "descripcion": "Total."}},
    },
}


def _dictionary(tmp_path: Path):  # noqa: ANN202
    (tmp_path / "CuentaPagar.json").write_text(json.dumps(_COMPRAS), encoding="utf-8")
    return load_dictionary(tmp_path)


def test_the_exact_table_returns_its_full_card_with_the_draft_flag(tmp_path: Path) -> None:
    result = _dictionary(tmp_path).search('"CuentaPagar"."FacturaIndicadorRetencionCompra"')

    card = result["tabla"]
    assert card["validado"] is False
    assert card["columnas"][0] == {
        "nombre": "valorRetencion",
        "tipo": "numeric",
        "descripcion": "Valor retenido.",
    }
    assert card["apunta_a"] == ["idFacturaCompra -> CuentaPagar.FacturaCompra(idFacturaCompra)"]


def test_a_topic_finds_the_tables_without_accents_and_ranks_names_first(tmp_path: Path) -> None:
    result = _dictionary(tmp_path).search("retención de compras")

    assert [m["tabla"] for m in result["matches"]] == [
        "CuentaPagar.FacturaIndicadorRetencionCompra",
        "CuentaPagar.FacturaCompra",
    ]


def test_an_unknown_topic_says_to_explore_the_schema(tmp_path: Path) -> None:
    result = _dictionary(tmp_path).search("depreciacion")

    assert result["matches"] == []
    assert "explore el esquema" in result["nota"]


def test_without_files_the_dictionary_is_empty(tmp_path: Path) -> None:
    assert len(load_dictionary(tmp_path / "no-existe")) == 0


async def test_tablas_erp_is_a_tipo_of_the_knowledge_tool_and_only_for_admins(
    tmp_path: Path,
) -> None:
    from app.modules.auth.domain.value_objects.module_code import ModuleCode
    from app.modules.chat.infrastructure.llm.tools.knowledge import (
        KNOWLEDGE_TIPOS,
        build_consultar_conocimiento_impl,
    )
    from app.modules.knowledge.infrastructure.static_catalog import load_static_catalog

    dictionary = _dictionary(tmp_path)
    (tmp_path / "catalogo").mkdir()
    catalog = load_static_catalog(tmp_path / "catalogo")
    admin = build_consultar_conocimiento_impl(catalog, None, erp_dictionary=dictionary)
    user = build_consultar_conocimiento_impl(
        catalog, frozenset({ModuleCode.CUENTAPAGAR}), erp_dictionary=dictionary
    )
    args = {"tipo": "tablas_erp", "consulta": "CuentaPagar.FacturaCompra"}

    assert "tablas_erp" in KNOWLEDGE_TIPOS
    assert (await admin(args))["tabla"]["tabla"] == "CuentaPagar.FacturaCompra"
    assert "solo para administradores" in (await user(args))["nota"]


def test_the_free_sql_rules_send_the_model_to_the_dictionary_first() -> None:
    from datetime import date

    from app.modules.chat.infrastructure.llm.system_prompt import build_system_prompt

    prompt = build_system_prompt(date(2026, 11, 25))

    assert prompt.index('`tipo: "tablas_erp"`') < prompt.index("explora ANTES de inventar")


def test_plurals_match_singular_table_names() -> None:
    from app.modules.knowledge.infrastructure.erp_dictionary import stem

    assert [stem(w) for w in ("retenciones", "compras", "facturas", "naturaleza", "iva")] == [
        "retencion",
        "compra",
        "factura",
        "naturaleza",
        "iva",
    ]


def test_the_shipped_dictionary_finds_the_withholdings_of_a_purchase() -> None:
    from app.modules.knowledge.infrastructure.erp_dictionary import get_erp_dictionary

    result = get_erp_dictionary().search("retenciones de compras")

    assert result["matches"][0]["tabla"] == "CuentaPagar.FacturaIndicadorRetencionCompra"
