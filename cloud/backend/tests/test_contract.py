"""Contrato `sync/v1`: cada fixture se valida contra el JSON Schema **y** el modelo Pydantic."""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import BaseModel, ValidationError

from app.shared.sync_v1 import (
    EVENT_MODELS,
    ConversationEvent,
    DatabaseEvent,
    EnrollRequest,
    EnrollResponse,
    FreeQueryEvent,
    HeartbeatRequest,
    HeartbeatResponse,
    IngestRequest,
    IngestResponse,
    SessionEvent,
    TurnEvent,
)
from tests.contract_files import (
    CONTRACT_DIR,
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


def test_every_pydantic_model_has_a_schema_and_vice_versa() -> None:
    assert set(MODELS) == set(list_schema_stems())


@pytest.mark.parametrize("stem", sorted(MODELS))
def test_schema_is_a_valid_json_schema(stem: str) -> None:
    Draft202012Validator.check_schema(load_json(schema_path(stem)))


@pytest.mark.parametrize("stem", sorted(MODELS))
def test_each_schema_has_valid_and_invalid_fixtures(stem: str) -> None:
    kinds = {f.valid for f in FIXTURES if f.stem == stem}
    assert kinds == {True, False}, f"{stem}: faltan fixtures válidos o inválidos"


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
            stem = event["schema"].split("/")[0]
            validate_document(stem, event)
            EVENT_MODELS[event["schema"]].model_validate(event)


def test_event_schema_names_cover_every_stream_version() -> None:
    declared = {
        load_json(schema_path(s))["properties"]["schema"]["const"]
        for s in ("turn", "conversation", "session", "free_query", "database")
    }
    assert declared == set(EVENT_MODELS)
