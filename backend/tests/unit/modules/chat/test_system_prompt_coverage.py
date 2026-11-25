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


def test_free_sql_rules_do_not_cap_a_full_listing_at_50_rows() -> None:
    # Fase 3 (C3.1): el prompt decía "LIMIT obligatorio, máximo 50" y el modelo
    # escribía LIMIT 50 en listados completos; el Excel salía con 50 filas
    # aunque la herramienta guarda hasta 10.000.
    free_sql = PROMPT[PROMPT.index("## SQL libre") :]
    assert "máximo 50" not in free_sql
    assert "sin `LIMIT`" in free_sql
    # Reglas viejas que ya no aplican: WITH se permite y el tope es por costo.
    assert "sin `WITH`" not in free_sql
    assert "≤ 1000 filas" not in free_sql


def test_a_full_listing_is_delivered_not_refused() -> None:
    # Prueba del 2026-11-25: "el plan de cuentas completo para Excel" respondió
    # "No puedo entregarle aquí el listado completo" por dos reglas de antes de
    # la exportación ("NO lo hagas", "no lo hagas ni con SQL libre").
    assert "NO lo\n  hagas" not in PROMPT
    assert "**no lo hagas** ni con" not in PROMPT
    assert "volcados completos" not in PROMPT
    assert "consulta sin achicar el límite" in PROMPT


def test_free_sql_translates_booleans_and_codes_for_the_excel() -> None:
    # El plan de cuentas salió con la naturaleza como "true".
    assert "traducido con `CASE`" in PROMPT


def test_the_name_as_it_appears_in_the_erp_is_copied_verbatim() -> None:
    # Escribió "VÁSQUEZ" con tilde y dijo que así figuraba; en el ERP no la tiene.
    assert "letra por letra" in COVERAGE
