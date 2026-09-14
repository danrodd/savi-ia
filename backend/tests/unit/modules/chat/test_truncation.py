from __future__ import annotations

from app.modules.chat.domain.entities import TextDeltaEvent
from app.modules.chat.infrastructure.llm.truncation import TRUNCATION_NOTICE, ResponseTruncator


def _texts(events: list[TextDeltaEvent]) -> list[str]:
    return [e.text for e in events]


def test_text_under_the_limit_passes_through() -> None:
    truncator = ResponseTruncator(max_chars=10)

    assert _texts(truncator.feed("hola")) == ["hola"]
    assert truncator.truncated is False


def test_cuts_exactly_at_the_limit_and_adds_notice_once() -> None:
    truncator = ResponseTruncator(max_chars=5)

    first = _texts(truncator.feed("abc"))
    second = _texts(truncator.feed("defgh"))
    third = _texts(truncator.feed("ijk"))

    assert first == ["abc"]
    assert second == ["de", TRUNCATION_NOTICE]
    assert third == []
    assert truncator.truncated is True


def test_chunk_after_reaching_the_limit_exactly_only_adds_the_notice() -> None:
    truncator = ResponseTruncator(max_chars=3)

    assert _texts(truncator.feed("abc")) == ["abc"]
    assert _texts(truncator.feed("d")) == [TRUNCATION_NOTICE]
    assert _texts(truncator.feed("e")) == []
