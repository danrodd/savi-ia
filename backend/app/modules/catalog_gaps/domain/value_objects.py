"""Vacíos del catálogo de datos: preguntas que el catálogo no alcanzó a responder.

Tres señales, todas de la propia instalación:

- `free_query`: la pregunta se resolvió con SQL libre (el catálogo no la cubre).
- `failed_query`: la consulta libre se rechazó o falló.
- `query_limit`: el turno gastó el cupo de consultas al ERP.

El texto de las preguntas no sale de la instalación: este reporte es local.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class GapKind(StrEnum):
    FREE_QUERY = "free_query"
    FAILED_QUERY = "failed_query"
    QUERY_LIMIT = "query_limit"


@dataclass(frozen=True, slots=True)
class GapEvent:
    """Una señal de un turno: qué pasó, con qué pregunta y qué tablas tocó."""

    kind: GapKind
    question: str
    conversation_id: UUID
    occurred_at: datetime
    tables: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CatalogGap:
    """Una pregunta (normalizada) con todo lo que le pasó en el periodo."""

    question: str
    kinds: tuple[GapKind, ...]
    times: int
    last_at: datetime
    tables: tuple[str, ...]
    conversation_id: UUID


@dataclass(frozen=True, slots=True)
class TableCount:
    table: str
    times: int


@dataclass(frozen=True, slots=True)
class CatalogGapReport:
    start: datetime
    end: datetime
    # Turnos por tipo de vacío (un turno puede tener más de uno).
    totals: dict[GapKind, int]
    gaps: tuple[CatalogGap, ...]
    top_tables: tuple[TableCount, ...]
