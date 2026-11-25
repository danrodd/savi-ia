"""El título de la tarjeta (y del archivo exportado) lo lee el usuario.

En la prueba del 2026-11-25 salió "Anticipos · Tercero id 41, Pendiente True":
un id interno y un booleano en inglés.
"""

from __future__ import annotations

from app.modules.data_query.application.query_parser import parse_semantic_query
from app.modules.data_query.application.run_semantic_query import (
    _title,  # pyright: ignore[reportPrivateUsage]
)
from app.modules.data_query.infrastructure.catalog import get_entity


def _title_for(raw: dict[str, object]) -> str:
    entity = get_entity(str(raw["entidad"]))
    assert entity is not None
    return _title(parse_semantic_query(raw), entity)


def test_internal_ids_and_booleans_do_not_reach_the_title() -> None:
    title = _title_for(
        {
            "entidad": "anticipos",
            "modo": "detalle",
            "filtros": [
                {"campo": "tercero_id", "op": "=", "valor": 41},
                {"campo": "pendiente", "op": "=", "valor": True},
            ],
        }
    )

    assert title == "Anticipos · Pendiente"


def test_a_false_boolean_reads_as_without() -> None:
    title = _title_for(
        {
            "entidad": "anticipos",
            "modo": "detalle",
            "filtros": [{"campo": "pendiente", "op": "=", "valor": False}],
        }
    )

    assert title == "Anticipos · Sin pendiente"


def test_new_entities_have_a_spanish_title() -> None:
    title = _title_for({"entidad": "devoluciones_venta", "modo": "detalle"})

    assert title == "Devoluciones en venta"
