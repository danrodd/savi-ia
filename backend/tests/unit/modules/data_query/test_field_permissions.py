"""Datos del tercero por permiso del ERP (P1 de los hallazgos de la primera demo).

- Personal (teléfonos, correo, NIT...): administrador o módulo TERCERO.
- Bancario: administrador o módulo CUENTAPAGAR.
- Sin permiso, el campo ni se ofrece y pedirlo devuelve un rechazo fijo, sin ir
  a la base.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.chat.infrastructure.llm.tools.consultar_datos import build_description
from app.modules.data_query.application import run_semantic_query as runner
from app.modules.data_query.application.permission_text import PERMISSION_DENIED_MARK
from app.modules.data_query.application.query_compiler import compile_query
from app.modules.data_query.application.query_parser import parse_semantic_query
from app.modules.data_query.infrastructure.catalog import get_entity

SALES = frozenset({"VENTA", "CUENTACOBRAR", "INVENTARIO"})
SALES_AND_TERCEROS = SALES | {"TERCERO"}


def _terceros():
    entity = get_entity("terceros")
    assert entity is not None
    return entity


def test_contact_fields_are_hidden_without_the_terceros_module() -> None:
    scoped = _terceros().scoped_for(SALES)

    assert "celular" not in scoped.fields
    assert "cuentas_bancarias" not in scoped.fields
    # Lo de negocio sigue.
    assert "municipio" in scoped.fields and "nombre" in scoped.fields


def test_the_terceros_module_shows_contact_but_not_bank_accounts() -> None:
    scoped = _terceros().scoped_for(SALES_AND_TERCEROS)

    assert {"celular", "telefono", "email", "direccion", "identificacion"} <= set(scoped.fields)
    assert "cuentas_bancarias" not in scoped.fields
    assert "cuentas_bancarias" in _terceros().scoped_for(SALES | {"CUENTAPAGAR"}).fields


def test_the_admin_sees_everything_without_the_vip_guard() -> None:
    entity = _terceros().scoped_for(None)

    assert "cuentas_bancarias" in entity.fields
    assert "TerceroVip" not in entity.fields["celular"].sql


def test_a_non_admin_gets_the_vip_guard_on_personal_data() -> None:
    scoped = _terceros().scoped_for(SALES_AND_TERCEROS)

    assert '"Seguridad"."TerceroVip"' in scoped.fields["celular"].sql


def test_contact_is_not_part_of_the_default_listing() -> None:
    query = parse_semantic_query({"entidad": "terceros", "modo": "detalle"})
    compiled = compile_query(query, _terceros().scoped_for(None))

    assert "celular" not in compiled.sql


def test_buyers_of_a_product_can_come_with_their_phone_in_one_query() -> None:
    entity = get_entity("ventas_detalle")
    assert entity is not None
    query = parse_semantic_query(
        {
            "entidad": "ventas_detalle",
            "modo": "agregado",
            "metricas": [next(iter(entity.metrics))],
            "dimensiones": ["cliente", "celular"]
            if "cliente" in entity.dimensions
            else ["celular"],
        }
    )

    compiled = compile_query(query, entity.scoped_for(SALES_AND_TERCEROS))

    assert '"celular"' in compiled.sql


async def test_asking_for_a_hidden_field_is_refused_without_touching_the_erp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def must_not_run(*_: Any, **__: Any) -> None:
        raise AssertionError("no debería consultar la base")

    monkeypatch.setattr(runner, "execute_compiled", must_not_run)

    text = await runner.run_semantic_query(
        {"entidad": "terceros", "modo": "detalle", "campos": ["nombre", "celular"]},
        modules=SALES,
    )

    assert text.startswith(PERMISSION_DENIED_MARK)
    assert "módulo Terceros" in text
    assert "NO vuelvas a intentarlo" in text


def test_the_tool_description_does_not_offer_what_the_user_cannot_see() -> None:
    without = build_description(SALES)
    with_terceros = build_description(SALES_AND_TERCEROS)

    assert "celular (Celular)" not in without
    assert "no puede ver" in without
    assert "celular (Celular)" in with_terceros


async def test_returning_personal_data_is_audited_without_the_values(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from app.modules.data_query.domain.query_result import QueryResult
    from app.modules.data_query.domain.semantic_query import QueryMode

    async def fake_execute(*_: Any, **__: Any) -> QueryResult:
        row = {"nombre": "EDWIN CHAVARRO", "celular": "3132622299"}
        return QueryResult(
            entidad="terceros", modo=QueryMode.DETAIL, columns=list(row), rows=[row], row_count=1
        )

    monkeypatch.setattr(runner, "execute_compiled", fake_execute)

    with caplog.at_level("INFO", logger="savi.audit"):
        await runner.run_semantic_query(
            {"entidad": "terceros", "modo": "detalle", "campos": ["nombre", "celular"]},
            modules=SALES_AND_TERCEROS,
        )

    assert "personal_data_access" in caplog.text and "fields=celular" in caplog.text
    assert "3132622299" not in caplog.text
