from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.company_knowledge.domain.services import (
    CitationRegistry,
    CitedChunk,
    format_pages,
)
from app.modules.company_knowledge.infrastructure.index.tokenizer import tokenize

DOC_A = uuid4()
DOC_B = uuid4()


def _chunk(document_id=DOC_A, ordinal=0, pages=(3, 4), title="Manual de caja") -> CitedChunk:  # type: ignore[no-untyped-def]
    return CitedChunk(document_id, 1, title, ordinal, pages[0], pages[1])


def test_same_chunk_keeps_its_reference_within_the_turn() -> None:
    registry = CitationRegistry()
    first = registry.register(_chunk())
    second = registry.register(_chunk(ordinal=1))
    assert (first, second) == ("D1", "D2")
    assert registry.register(_chunk()) == "D1"


def test_sources_group_by_document_in_order_of_appearance_and_join_pages() -> None:
    registry = CitationRegistry()
    registry.register(_chunk(ordinal=0, pages=(3, 4)))  # D1
    registry.register(_chunk(document_id=DOC_B, title="Política", pages=(2, 2)))  # D2
    registry.register(_chunk(ordinal=5, pages=(9, 9)))  # D3

    sources = registry.build_sources(
        "Firma el supervisor [D2]. Cierre diario [D3] y [D1]. Otra vez [D1]."
    )

    assert [s.title for s in sources] == ["Política", "Manual de caja"]
    manual = sources[1]
    assert manual.refs == ("D3", "D1")
    assert manual.pages == "3-4, 9"


def test_invented_references_are_discarded() -> None:
    registry = CitationRegistry()
    registry.register(_chunk())
    sources = registry.build_sources("Dato real [D1]. Dato inventado [D7].")
    assert [s.refs for s in sources] == [("D1",)]


def test_no_references_no_sources() -> None:
    registry = CitationRegistry()
    registry.register(_chunk())
    assert registry.build_sources("Respuesta sin citas.") == []


@pytest.mark.parametrize(
    ("ranges", "expected"),
    [
        ([(3, 4), (9, 9), (4, 5)], "3-5, 9"),
        ([(1, 1)], "1"),
        ([(None, None)], None),
        ([(2, None)], "2"),
    ],
)
def test_format_pages(ranges: list[tuple[int | None, int | None]], expected: str | None) -> None:
    assert format_pages(ranges) == expected


def test_tokenizer_strips_accents_and_stopwords() -> None:
    assert tokenize("La facturación de las Órdenes") == ["facturacion", "ordenes"]


def test_tokenizer_keeps_compound_codes_and_their_parts() -> None:
    tokens = tokenize("Según el acta POL-DSC-19")
    assert {"pol", "dsc", "19", "poldsc19"}.issubset(tokens)
