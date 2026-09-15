"""Avance del procesamiento (Fase 4, O5).

Un PDF de 500 páginas tarda casi dos minutos y la interfaz solo podía decir
"Procesando…". El avance vive en memoria del proceso: solo significa algo
mientras el documento se procesa, y si SAVI se reinicia el documento vuelve a
la cola.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.company_knowledge.infrastructure.progress import (
    Progress,
    ProgressRegistry,
)


@pytest.fixture
def registro() -> ProgressRegistry:
    return ProgressRegistry()


def test_unknown_document_has_no_progress(registro: ProgressRegistry) -> None:
    assert registro.get(uuid4()) is None


def test_start_sets_the_total_and_zero_done(registro: ProgressRegistry) -> None:
    documento = uuid4()

    registro.start(documento, 120)

    assert registro.get(documento) == Progress(0, 120)


def test_advance_updates_only_the_done_count(registro: ProgressRegistry) -> None:
    documento = uuid4()
    registro.start(documento, 120)

    registro.advance(documento, 64)

    assert registro.get(documento) == Progress(64, 120)


def test_advance_on_an_unknown_document_is_ignored(registro: ProgressRegistry) -> None:
    """Un documento que ya terminó no puede resucitar su barra."""
    registro.advance(uuid4(), 10)

    assert registro.get(uuid4()) is None


def test_finish_clears_it(registro: ProgressRegistry) -> None:
    """Si quedara colgado, la interfaz mostraría un porcentaje viejo para
    siempre."""
    documento = uuid4()
    registro.start(documento, 120)
    registro.advance(documento, 120)

    registro.finish(documento)

    assert registro.get(documento) is None


def test_documents_do_not_interfere(registro: ProgressRegistry) -> None:
    uno, otro = uuid4(), uuid4()
    registro.start(uno, 10)
    registro.start(otro, 100)

    registro.advance(uno, 5)

    assert registro.get(uno) == Progress(5, 10)
    assert registro.get(otro) == Progress(0, 100)


@pytest.mark.parametrize(
    ("done", "total", "esperado"),
    [(0, 100, 0), (50, 100, 50), (100, 100, 100), (3, 7, 43), (0, 0, 0), (150, 100, 100)],
)
def test_percent(done: int, total: int, esperado: int) -> None:
    """`total = 0` no puede dividir por cero, y nunca pasa de 100."""
    assert Progress(done, total).percent == esperado
