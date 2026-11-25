"""Agrupa las señales por pregunta: lo que lee quien decide qué sumar al catálogo."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from app.modules.catalog_gaps.domain.value_objects import (
    CatalogGap,
    CatalogGapReport,
    GapEvent,
    GapKind,
    TableCount,
)

MAX_GAPS = 500
TOP_TABLES = 15
_SPACES = re.compile(r"\s+")
_EDGES = "¿?¡!.,;: \"'"


def question_key(question: str) -> str:
    """ "¿Cuánto vendimos en marzo?" y "cuánto vendimos en marzo" son la misma."""
    return _SPACES.sub(" ", question.casefold()).strip(_EDGES)


def build_report(events: Sequence[GapEvent], start: datetime, end: datetime) -> CatalogGapReport:
    # Un turno (conversación + pregunta) cuenta una vez por tipo aunque haya
    # hecho varias consultas libres.
    turns: dict[tuple[UUID, str, GapKind], GapEvent] = {}
    for event in sorted(events, key=lambda e: e.occurred_at):
        key = question_key(event.question)
        if not key:
            continue
        slot = (event.conversation_id, key, event.kind)
        previous = turns.get(slot)
        tables = tuple(sorted({*(previous.tables if previous else ()), *event.tables}))
        turns[slot] = GapEvent(
            kind=event.kind,
            question=event.question,
            conversation_id=event.conversation_id,
            occurred_at=event.occurred_at,
            tables=tables,
        )

    totals = Counter(kind for _, _, kind in turns)
    grouped: dict[str, list[GapEvent]] = {}
    for (_, key, _), event in turns.items():
        grouped.setdefault(key, []).append(event)

    gaps: list[CatalogGap] = []
    table_turns: Counter[str] = Counter()
    for group in grouped.values():
        latest = max(group, key=lambda e: e.occurred_at)
        tables = sorted({t for e in group for t in e.tables})
        # Veces = conversaciones distintas con esa pregunta: regenerarla en la
        # misma conversación no la vuelve más frecuente.
        times = len({e.conversation_id for e in group})
        gaps.append(
            CatalogGap(
                question=latest.question.strip(),
                kinds=tuple(sorted({e.kind for e in group}, key=list(GapKind).index)),
                times=times,
                last_at=latest.occurred_at,
                tables=tuple(tables),
                conversation_id=latest.conversation_id,
            )
        )
    for event in turns.values():
        table_turns.update(event.tables)

    gaps.sort(key=lambda g: (-g.times, -g.last_at.timestamp()))
    return CatalogGapReport(
        start=start,
        end=end,
        totals={kind: totals.get(kind, 0) for kind in GapKind},
        gaps=tuple(gaps[:MAX_GAPS]),
        top_tables=tuple(TableCount(t, n) for t, n in table_turns.most_common(TOP_TABLES)),
    )
