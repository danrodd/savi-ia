"""`UsageFilters` — normalización de las dimensiones multi-valor."""
from __future__ import annotations

from app.modules.usage.domain.value_objects import UsageFilters


def test_empty_filters_mean_no_restriction() -> None:
    filters = UsageFilters()
    assert filters.providers == frozenset()
    assert filters.models == frozenset()


def test_strips_whitespace_and_drops_blanks() -> None:
    filters = UsageFilters(providers=frozenset({" claude ", "", "gemini"}), models=frozenset({" "}))
    assert filters.providers == frozenset({"claude", "gemini"})
    assert filters.models == frozenset()


def test_accepts_more_than_one_provider() -> None:
    filters = UsageFilters(providers=frozenset({"claude", "gemini", "openai"}))
    assert len(filters.providers) == 3
