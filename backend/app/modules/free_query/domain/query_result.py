"""Resultado de una ejecución de SQL libre."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _empty_rows() -> list[dict[str, Any]]:
    return []


def _empty_str_list() -> list[str]:
    return []


@dataclass(slots=True)
class QueryResult:
    columns: list[str] = field(default_factory=_empty_str_list)
    rows: list[dict[str, Any]] = field(default_factory=_empty_rows)
    estimated_rows: int = 0
    returned_rows: int = 0
    duration_ms: int = 0
    truncated: bool = False
    # El SQL efectivamente ejecutado (puede diferir del input si se
    # sobrescribió el LIMIT). Útil para auditoría.
    executed_sql: str = ""
