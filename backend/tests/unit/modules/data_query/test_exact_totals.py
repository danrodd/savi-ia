"""Total exacto cuando una consulta pasa del tope que se guarda.

Antes se informaba "más de 10.000". Ahora se cuenta el total real con la misma
consulta sin su `LIMIT`, y el conjunto lo guarda aunque conserve solo las
primeras filas.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.modules.data_query.application import run_semantic_query as runner
from app.modules.data_query.domain.query_result import QueryResult
from app.modules.data_query.domain.semantic_query import QueryMode
from app.modules.documents.domain.document import Document
from app.modules.documents.domain.result_set import EXPORT_MAX_ROWS, build_result_set
from app.modules.documents.infrastructure.exporters import (
    _total_note,  # pyright: ignore[reportPrivateUsage]
)
from app.modules.free_query.application.formatter import format_result
from app.modules.free_query.domain.query_result import QueryResult as FreeQueryResult


async def test_the_catalog_counts_the_real_total_when_rows_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_execute(compiled: Any, entidad: str, modo: QueryMode, **_: Any) -> QueryResult:
        rows = [{"nombre": f"Cliente {i}"} for i in range(6)]
        return QueryResult(entidad=entidad, modo=modo, columns=["nombre"], rows=rows, row_count=6)

    async def fake_count(compiled: Any, **_: Any) -> int:
        return 5343

    saved: dict[str, Any] = {}

    async def recorder(
        title: str,
        keys: list[str],
        labels: dict[str, str],
        rows: list[dict[str, Any]],
        personal: bool,
        exact: int | None,
    ) -> str:
        saved.update(rows=len(rows), exact=exact)
        return "c-1"

    monkeypatch.setattr(runner, "execute_compiled", fake_execute)
    monkeypatch.setattr(runner, "count_compiled", fake_count)

    text = await runner.run_semantic_query(
        {"entidad": "terceros", "modo": "detalle", "campos": ["nombre"], "limite": 3},
        modules=None,
        recorder=recorder,
        full_fetch=5,
    )

    assert saved == {"rows": 6, "exact": 5343}
    assert "Mostrando 3 de 5.343 filas" in text
    # El separador de miles va solo en el número; la frase conserva sus comas.
    assert "debajo de tu respuesta, con el botón Exportar" in text
    assert "Excel, PDF o CSV" in text


def test_the_result_set_keeps_the_counted_total() -> None:
    rows = [{"x": i} for i in range(EXPORT_MAX_ROWS + 1)]

    table = build_result_set(
        conversation_id=uuid4(),
        title="Muchos",
        keys=["x"],
        labels={},
        raw_rows=rows,
        has_personal_data=False,
        exact_total=52_000,
    )

    assert len(table.rows) == EXPORT_MAX_ROWS
    assert table.total_rows == 52_000
    assert not table.total_is_lower_bound
    assert _total_note(table) == "Primeras 10.000 filas de 52.000."
    assert Document  # el documento usa la misma nota


def test_the_free_query_reports_the_counted_total() -> None:
    result = FreeQueryResult(
        columns=["codigo"],
        rows=[{"codigo": i} for i in range(60)],
        returned_rows=60,
        truncated=True,
        total_rows=18_250,
    )

    payload = format_result(result, shown=50, kept=True, result_set_id="c-2")

    assert "Ves 50 de 18250 filas" in payload
    assert '"conjunto": "c-2"' in payload
