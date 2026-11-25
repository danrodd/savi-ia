"""Borrador del diccionario: al modelo solo le llega la estructura, nunca datos."""

from __future__ import annotations

import json

from scripts.erp_dictionary.draft import build_payload, parse_draft

_TABLE = {
    "module": "Contabilidad",
    "comment": None,
    "primary_key": ["idAnticipo"],
    "columns": [
        {"name": "idAnticipo", "type": "integer", "nullable": False, "comment": None},
        {"name": "saldoAnticipo", "type": "numeric", "nullable": True, "comment": "Por cruzar"},
    ],
    "foreign_keys": [
        {"columns": ["idTercero"], "references": "Tercero.Tercero", "ref_columns": ["idTercero"]}
    ],
    "referenced_by": ["Cartera.CruceAnticipoCliente(idAnticipo)"],
    "usage": {"present_in": 4, "with_data": 3, "max_rows": 2343},
    "functions": ["Cartera.fnRecalcularCarteraCliente"],
}


def test_the_payload_is_only_structure_and_rounds_the_size() -> None:
    payload = build_payload("Contabilidad.Anticipo", _TABLE, bases=4)

    assert payload["tabla"] == "Contabilidad.Anticipo"
    assert payload["apunta_a"] == ["idTercero -> Tercero.Tercero(idTercero)"]
    assert payload["uso"] == "con datos en 3 de 4 bases; del orden de 10^3 filas"
    # Ni el conteo exacto ni nada que no sea la estructura.
    text = json.dumps(payload, ensure_ascii=False)
    assert "2343" not in text
    assert set(payload) == {
        "tabla",
        "comentario_en_la_base",
        "clave_primaria",
        "columnas",
        "apunta_a",
        "la_referencian",
        "funciones_que_la_usan",
        "uso",
    }


def test_the_model_answer_is_normalised_to_every_column() -> None:
    answer = """```json
    {"descripcion": " Anticipos de clientes y proveedores. ",
     "columnas": {"saldoAnticipo": "Lo que falta cruzar", "inventada": "x"},
     "dudas": ["¿Cuándo queda en cero?", "", "b", "c", "d", "e", "f"]}
    ```"""

    draft = parse_draft(answer, ["idAnticipo", "saldoAnticipo"])

    assert draft["descripcion"] == "Anticipos de clientes y proveedores."
    assert draft["columnas"] == {"idAnticipo": "", "saldoAnticipo": "Lo que falta cruzar"}
    assert draft["dudas"][0] == "¿Cuándo queda en cero?"
    assert len(draft["dudas"]) == 5
