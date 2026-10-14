"""Acceso a `contracts/sync/v1/` (esquemas y fixtures) para los tests."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

# backend/tests/unit/modules/cloud_link/contract_files.py -> raíz del monorepo.
CONTRACT_DIR = Path(__file__).resolve().parents[5] / "contracts" / "sync" / "v1"
FIXTURES_DIR = CONTRACT_DIR / "fixtures"
EVENTS_DIR = CONTRACT_DIR / "events"

EVENT_STEMS = ("turn", "conversation", "session", "free_query", "database")

_FIXTURE_NAME = re.compile(r"^(?P<stem>.+)\.(?P<kind>valid|invalid)\.(?P<case>[a-z0-9_]+)\.json$")


def schema_path(stem: str) -> Path:
    base = EVENTS_DIR if stem in EVENT_STEMS else CONTRACT_DIR
    return base / f"{stem}.schema.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Fixture:
    path: Path
    stem: str
    valid: bool

    @property
    def id(self) -> str:
        return self.path.name


def list_fixtures() -> list[Fixture]:
    found: list[Fixture] = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        match = _FIXTURE_NAME.match(path.name)
        if match is None:
            raise AssertionError(f"Nombre de fixture inválido: {path.name}")
        found.append(Fixture(path, match["stem"], match["kind"] == "valid"))
    return found


def list_schema_stems() -> list[str]:
    stems = [p.name.removesuffix(".schema.json") for p in CONTRACT_DIR.glob("*.schema.json")]
    stems += [p.name.removesuffix(".schema.json") for p in EVENTS_DIR.glob("*.schema.json")]
    return sorted(stems)


def validate_document(stem: str, document: Any) -> None:
    """Valida contra el JSON Schema de `stem`; levanta `jsonschema.ValidationError`."""
    validator = Draft202012Validator(load_json(schema_path(stem)), format_checker=FormatChecker())
    validator.validate(document)  # pyright: ignore[reportUnknownMemberType]
