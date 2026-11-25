"""El prompt dice qué datos cubre el catálogo y cómo no dar un dato falso.

Reporte de soporte del 2026-11-24: el modelo revisó cartera, no encontró el
anticipo de una clienta y respondió que no había documentos. No sabía que los
anticipos estaban en otra parte ni que "no lo encontré" no es "no existe".
"""

from __future__ import annotations

from datetime import date

from app.modules.chat.infrastructure.llm.system_prompt import build_system_prompt
from app.modules.data_query.infrastructure.catalog import entity_names

PROMPT = build_system_prompt(date(2026, 11, 25))
_START = PROMPT.index("## Qué datos puedes consultar y cuáles no")
COVERAGE = PROMPT[_START : PROMPT.index("## SQL libre", _START)]


def test_every_catalog_entity_is_listed_in_the_coverage_section() -> None:
    # Una entidad nueva sin nombrar acá es una que el modelo no sabe que tiene.
    missing = [name for name in entity_names() if f"`{name}`" not in COVERAGE]
    assert missing == []


def test_the_coverage_section_names_what_is_not_in_the_catalog() -> None:
    for outside in ("contabilidad general", "nómina", "activos fijos"):
        assert outside in COVERAGE


def test_the_rules_forbid_turning_not_found_into_does_not_exist() -> None:
    assert "NUNCA" in COVERAGE
    assert "concluyas que el dato no existe" in COVERAGE
    assert "Nunca pidas una captura" in COVERAGE
    assert "anticipos" in COVERAGE


def test_an_empty_free_query_says_where_it_looked() -> None:
    # Prueba del 2026-11-25: "no encontré depreciaciones este mes", con la
    # tabla vacía del todo y sin decir dónde buscó.
    assert "Si `consultar_libre` no devuelve nada" in COVERAGE
    assert "el ERP no tiene ninguno" in COVERAGE


def test_the_name_as_it_appears_in_the_erp_is_copied_verbatim() -> None:
    # Escribió "VÁSQUEZ" con tilde y dijo que así figuraba; en el ERP no la tiene.
    assert "letra por letra" in COVERAGE
