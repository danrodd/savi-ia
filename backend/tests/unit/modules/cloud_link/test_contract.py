"""Contrato `sync/v1`: cada fixture se valida contra el JSON Schema **y** contra
el modelo Pydantic de la instancia (§8.1). Más el test de privacidad (RNF-04)."""

from __future__ import annotations

from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import BaseModel, ValidationError

from app.modules.cloud_link.infrastructure.contract_v1 import (
    EVENT_MODELS,
    ConversationData,
    ConversationEvent,
    DatabaseData,
    DatabaseEvent,
    EnrollRequest,
    EnrollResponse,
    FreeQueryData,
    FreeQueryEvent,
    HeartbeatRequest,
    HeartbeatResponse,
    IngestRequest,
    IngestResponse,
    SessionData,
    SessionEvent,
    ToolInvocation,
    TurnData,
    TurnEvent,
)

from .contract_files import (
    CONTRACT_DIR,
    EVENT_STEMS,
    EVENTS_DIR,
    Fixture,
    list_fixtures,
    list_schema_stems,
    load_json,
    schema_path,
    validate_document,
)

MODELS: dict[str, type[BaseModel]] = {
    "enroll.request": EnrollRequest,
    "enroll.response": EnrollResponse,
    "heartbeat.request": HeartbeatRequest,
    "heartbeat.response": HeartbeatResponse,
    "ingest.request": IngestRequest,
    "ingest.response": IngestResponse,
    "turn": TurnEvent,
    "conversation": ConversationEvent,
    "session": SessionEvent,
    "free_query": FreeQueryEvent,
    "database": DatabaseEvent,
}

FIXTURES = list_fixtures()


def test_contract_directory_has_the_documented_layout() -> None:
    assert (CONTRACT_DIR / "README.md").is_file()
    assert set(list_schema_stems()) == set(MODELS)


@pytest.mark.parametrize("stem", sorted(MODELS))
def test_schema_is_a_valid_json_schema(stem: str) -> None:
    Draft202012Validator.check_schema(load_json(schema_path(stem)))


@pytest.mark.parametrize("stem", sorted(MODELS))
def test_each_schema_has_valid_and_invalid_fixtures(stem: str) -> None:
    assert {f.valid for f in FIXTURES if f.stem == stem} == {True, False}


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.id)
def test_fixture_against_json_schema(fixture: Fixture) -> None:
    document = load_json(fixture.path)
    if fixture.valid:
        validate_document(fixture.stem, document)
    else:
        with pytest.raises(SchemaValidationError):
            validate_document(fixture.stem, document)


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.id)
def test_fixture_against_pydantic_model(fixture: Fixture) -> None:
    model = MODELS[fixture.stem]
    raw = fixture.path.read_text(encoding="utf-8")
    if fixture.valid:
        model.model_validate_json(raw)
    else:
        with pytest.raises(ValidationError):
            model.model_validate_json(raw)


def test_events_inside_valid_ingest_fixtures_match_their_event_schema() -> None:
    for fixture in (f for f in FIXTURES if f.stem == "ingest.request" and f.valid):
        for event in load_json(fixture.path)["events"]:
            validate_document(event["schema"].split("/")[0], event)
            EVENT_MODELS[event["schema"]].model_validate(event)


# ── privacidad (RNF-04, §8.1) ─────────────────────────────────────────────

ENVELOPE_FIELDS = {"schema", "source_id", "occurred_at", "data"}

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
        "name",
        "status",
        "tipo",
    },
    "conversation": {"conversation_ref", "database_ref", "user_ref"},
    "session": {"user_ref", "user_label", "database_ref"},
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


def _property_names(node: Any, found: set[str]) -> None:
    if isinstance(node, dict):
        mapping = cast(dict[str, Any], node)
        properties: Any = mapping.get("properties")
        if isinstance(properties, dict):
            for name, child in cast(dict[str, Any], properties).items():
                found.add(name)
                _property_names(child, found)
        for key, value in mapping.items():
            if key != "properties":
                _property_names(value, found)
    elif isinstance(node, list):
        for item in cast(list[Any], node):
            _property_names(item, found)


def _open_objects(node: Any, path: str = "$") -> list[str]:
    problems: list[str] = []
    if isinstance(node, dict):
        mapping = cast(dict[str, Any], node)
        if "properties" in mapping and mapping.get("additionalProperties") is not False:
            problems.append(path)
        for key, value in mapping.items():
            problems += _open_objects(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(cast(list[Any], node)):
            problems += _open_objects(item, f"{path}[{index}]")
    return problems


def _violations(stem: str, schema: dict[str, Any]) -> list[str]:
    data = schema["properties"]["data"]
    names: set[str] = set()
    _property_names(data, names)
    problems = [f"{n}: fuera de la lista blanca" for n in sorted(names - APPROVED_FIELDS[stem])]
    for name in sorted(names):
        problems += [f"{name}: contiene '{f}'" for f in FORBIDDEN_FRAGMENTS if f in name.lower()]
    problems += [f"{p}: additionalProperties debe ser false" for p in _open_objects(data)]
    problems += [
        f"{n}: campo de sobre no previsto"
        for n in sorted(set(schema["properties"]) - ENVELOPE_FIELDS)
    ]
    return problems


@pytest.mark.parametrize("stem", EVENT_STEMS)
def test_event_schema_only_has_whitelisted_fields(stem: str) -> None:
    assert _violations(stem, load_json(schema_path(stem))) == []


def test_all_event_schemas_are_checked() -> None:
    on_disk = {p.name.removesuffix(".schema.json") for p in EVENTS_DIR.glob("*.schema.json")}
    assert on_disk == set(EVENT_STEMS) == set(APPROVED_FIELDS)


def test_pydantic_models_expose_exactly_the_same_whitelist() -> None:
    models: dict[str, tuple[type[BaseModel], ...]] = {
        "turn": (TurnData, ToolInvocation),
        "conversation": (ConversationData,),
        "session": (SessionData,),
        "free_query": (FreeQueryData,),
        "database": (DatabaseData,),
    }
    for stem, classes in models.items():
        fields = {name for cls in classes for name in cls.model_fields}
        assert fields == APPROVED_FIELDS[stem], stem
