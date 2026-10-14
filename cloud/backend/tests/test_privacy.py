"""Privacidad (RNF-04, §8.1): los esquemas de eventos son una lista blanca cerrada.

Si este test falla porque alguien agregó un campo, no se "arregla" ampliando la lista: se
revisa primero que el campo no lleve contenido (preguntas, respuestas, SQL, credenciales,
datos del ERP) y recién entonces se aprueba aquí, en el mismo cambio que el contrato.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.shared.sync_v1 import (
    ConversationData,
    DatabaseData,
    FreeQueryData,
    SessionData,
    ToolInvocation,
    TurnData,
)
from tests.contract_files import EVENT_STEMS, EVENTS_DIR, load_json, schema_path

ENVELOPE_FIELDS = {"schema", "source_id", "occurred_at", "data"}

# Lista blanca aprobada de `data` por stream (§4). Incluye los campos de objetos anidados.
APPROVED_FIELDS: dict[str, set[str]] = {
    "turn": {
        "conversation_ref",
        "database_ref",
        "user_ref",
        "provider",
        "model",
        "finish_reason",
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "cost_usd",
        "tools",
        "latency_ms",
        "action",
        # elementos de `tools`: nunca el `input` de la invocación
        "name",
        "status",
        "tipo",
    },
    "conversation": {"conversation_ref", "database_ref", "user_ref"},
    "session": {"user_ref", "database_ref"},
    "free_query": {
        "conversation_ref",
        "database_ref",
        "result",
        "estimated_rows",
        "returned_rows",
        "duration_ms",
    },
    "database": {
        "database_ref",
        "code",
        "name",
        "is_active",
        "is_usable",
        "credentials_unreadable",
        "last_connection_ok_at",
    },
}

FORBIDDEN_FRAGMENTS = (
    "sql",
    "question",
    "content",
    "answer",
    "password",
    "host",
    "login",
    "full_name",
)


def collect_property_names(node: Any, names: set[str] | None = None) -> set[str]:
    """Todos los nombres de propiedad bajo `node`, a cualquier profundidad."""
    found: set[str] = set() if names is None else names
    if isinstance(node, dict):
        properties = node.get("properties")  # type: ignore[reportUnknownMemberType]
        if isinstance(properties, dict):
            for name, child in properties.items():  # type: ignore[reportUnknownVariableType]
                found.add(str(name))  # type: ignore[reportUnknownArgumentType]
                collect_property_names(child, found)
        for key, value in node.items():  # type: ignore[reportUnknownVariableType]
            if key != "properties":
                collect_property_names(value, found)
    elif isinstance(node, list):
        for item in node:  # type: ignore[reportUnknownVariableType]
            collect_property_names(item, found)
    return found


def open_objects(node: Any, path: str = "$") -> list[str]:
    """Rutas de objetos con `properties` que no cierran `additionalProperties`."""
    problems: list[str] = []
    if isinstance(node, dict):
        if "properties" in node and node.get("additionalProperties") is not False:  # type: ignore[reportUnknownMemberType]
            problems.append(path)
        for key, value in node.items():  # type: ignore[reportUnknownVariableType]
            problems += open_objects(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):  # type: ignore[reportUnknownVariableType]
            problems += open_objects(item, f"{path}[{index}]")
    return problems


def violations(stem: str, schema: dict[str, Any]) -> list[str]:
    data = schema["properties"]["data"]
    names = collect_property_names(data)
    problems = [f"{n}: fuera de la lista blanca" for n in sorted(names - APPROVED_FIELDS[stem])]
    for name in sorted(names):
        for fragment in FORBIDDEN_FRAGMENTS:
            if fragment in name.lower():
                problems.append(f"{name}: contiene '{fragment}'")
    problems += [f"{p}: additionalProperties debe ser false" for p in open_objects(data)]
    extra_envelope = set(schema["properties"]) - ENVELOPE_FIELDS
    problems += [f"{n}: campo de sobre no previsto" for n in sorted(extra_envelope)]
    return problems


@pytest.mark.parametrize("stem", EVENT_STEMS)
def test_event_schema_only_has_whitelisted_fields(stem: str) -> None:
    assert violations(stem, load_json(schema_path(stem))) == []


def test_all_event_schemas_are_checked() -> None:
    on_disk = {p.name.removesuffix(".schema.json") for p in EVENTS_DIR.glob("*.schema.json")}
    assert on_disk == set(EVENT_STEMS) == set(APPROVED_FIELDS)


def test_checker_detects_a_leaky_schema() -> None:
    leaky: dict[str, Any] = {
        "properties": {
            "schema": {},
            "source_id": {},
            "occurred_at": {},
            "data": {
                "type": "object",
                "properties": {
                    "conversation_ref": {},
                    "user_question": {},
                    "sql": {},
                    "db_host": {},
                },
            },
        }
    }
    found = violations("conversation", leaky)
    assert any("user_question: fuera" in p for p in found)
    assert any("sql: contiene 'sql'" in p for p in found)
    assert any("db_host: contiene 'host'" in p for p in found)
    assert any("additionalProperties" in p for p in found)


def test_pydantic_models_expose_exactly_the_same_whitelist() -> None:
    models = {
        "turn": (TurnData, ToolInvocation),
        "conversation": (ConversationData,),
        "session": (SessionData,),
        "free_query": (FreeQueryData,),
        "database": (DatabaseData,),
    }
    for stem, classes in models.items():
        fields = {name for cls in classes for name in cls.model_fields}
        assert fields == APPROVED_FIELDS[stem], stem
