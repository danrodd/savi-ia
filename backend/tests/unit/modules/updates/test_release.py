"""Dominio de la actualización: versión, manifiesto y qué se le muestra a cada equipo."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.updates.domain.exceptions import InvalidManifestError, InvalidVersionError
from app.modules.updates.domain.value_objects import (
    ReleaseManifest,
    ReleaseVersion,
    UpdateState,
    decide,
)

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


def _manifest(**overrides: object) -> ReleaseManifest:
    data: dict[str, object] = {
        "version": "v1.4.0",
        "published_at": "2026-11-02T15:00:00Z",
        "url": "https://updates.example.com/savi/releases/SAVI-Setup-v1.4.0.exe",
        "sha256": "a" * 64,
        "size": 170_082_699,
        "min_version": "v1.3.1",
        "min_version_from": "2026-11-05T15:00:00Z",
        "notes": "Corrige la pantalla en blanco.",
    }
    data.update(overrides)
    return ReleaseManifest.from_mapping(data)


# ------------------------------------------------------------------- versión


def test_version_parses_and_orders_numerically() -> None:
    assert ReleaseVersion.parse("v1.10.0") > ReleaseVersion.parse("v1.9.9")
    assert str(ReleaseVersion.parse("v1.3.2")) == "v1.3.2"


@pytest.mark.parametrize("text", ["1.3.2", "v1.3", "v1.3.2-sucio", "v1.3.2-3-gabc1234", ""])
def test_version_rejects_non_release_text(text: str) -> None:
    with pytest.raises(InvalidVersionError):
        ReleaseVersion.parse(text)


@pytest.mark.parametrize("text", ["0.0.0-dev", "v1.3.2-3-gabc1234", "v1.3.2-sucio", "abc1234"])
def test_development_builds_do_not_update(text: str) -> None:
    assert ReleaseVersion.from_running(text) is None


# ---------------------------------------------------------------- manifiesto


def test_manifest_reads_every_field() -> None:
    manifest = _manifest()
    assert manifest.version == ReleaseVersion(1, 4, 0)
    assert manifest.min_version_from == datetime(2026, 11, 5, 15, 0, tzinfo=UTC)
    assert manifest.size == 170_082_699


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": "1.4.0"},
        {"min_version": "v1.5.0"},
        {"url": "http://updates.example.com/SAVI-Setup.exe"},
        {"url": "ftp://updates.example.com/SAVI-Setup.exe"},
        {"sha256": "zz"},
        {"size": 0},
        {"size": True},
        {"size": "170"},
        {"min_version_from": "2026-11-05T15:00:00"},
        {"min_version_from": "mañana"},
        {"notes": 3},
        {"url": None},
    ],
)
def test_manifest_rejects_bad_fields(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidManifestError):
        _manifest(**overrides)


def test_manifest_allows_plain_http_only_on_loopback() -> None:
    manifest = _manifest(url="http://127.0.0.1:8765/releases/SAVI-Setup-v1.4.0.exe")
    assert manifest.url.startswith("http://127.0.0.1")


def test_manifest_normalizes_hash_case() -> None:
    assert _manifest(sha256="A" * 64).sha256 == "a" * 64


# ------------------------------------------------------------------ decisión


def test_same_version_is_up_to_date() -> None:
    decision = decide(ReleaseVersion(1, 4, 0), _manifest(), NOW)
    assert decision.state is UpdateState.UP_TO_DATE
    assert decision.manifest is None


def test_never_offers_a_downgrade() -> None:
    decision = decide(ReleaseVersion(1, 5, 0), _manifest(), NOW)
    assert decision.state is UpdateState.UP_TO_DATE


def test_newer_version_above_minimum_is_recommended() -> None:
    decision = decide(ReleaseVersion(1, 3, 2), _manifest(), NOW)
    assert decision.state is UpdateState.RECOMMENDED
    assert decision.deadline is None


def test_below_minimum_within_window_is_required_with_deadline() -> None:
    decision = decide(ReleaseVersion(1, 3, 0), _manifest(), NOW)
    assert decision.state is UpdateState.REQUIRED
    assert decision.deadline == datetime(2026, 11, 5, 15, 0, tzinfo=UTC)


def test_below_minimum_after_window_is_blocked() -> None:
    later = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)
    decision = decide(ReleaseVersion(1, 3, 0), _manifest(), later)
    assert decision.state is UpdateState.BLOCKED
    assert decision.deadline is None


def test_immediate_minimum_blocks_right_away() -> None:
    manifest = _manifest(min_version="v1.4.0", min_version_from="2026-11-02T15:00:00Z")
    decision = decide(ReleaseVersion(1, 3, 2), manifest, NOW + timedelta(seconds=1))
    assert decision.state is UpdateState.BLOCKED


# ---------------------------------------------------------------- candidatas


def test_candidates_order_before_their_final_version() -> None:
    ordered = ["v1.3.2", "v1.4.0-rc.1", "v1.4.0-rc.2", "v1.4.0-rc.10", "v1.4.0", "v1.4.1-rc.1"]
    versions = [ReleaseVersion.parse(text) for text in ordered]

    assert versions == sorted(versions)
    assert [str(version) for version in versions] == ordered
    assert ReleaseVersion.parse("v1.4.0-rc.2").is_candidate
    assert not ReleaseVersion.parse("v1.4.0").is_candidate


@pytest.mark.parametrize(
    "text",
    [
        "v1.4.0-rc",
        "v1.4.0-rc.0",
        "v1.4.0-rc.01",
        "v1.4.0-rc.1-3-gabc1234",
        "v1.4.0-rc.1-sucio",
        "v1.4.0-beta.1",
    ],
)
def test_malformed_candidates_are_rejected(text: str) -> None:
    with pytest.raises(InvalidVersionError):
        ReleaseVersion.parse(text)


def test_an_exact_candidate_updates_but_a_build_on_top_of_it_does_not() -> None:
    assert ReleaseVersion.from_running("v1.4.0-rc.1") == ReleaseVersion(1, 4, 0, 1)
    assert ReleaseVersion.from_running("v1.4.0-rc.1-3-gabc1234") is None
    assert ReleaseVersion.from_running("v1.4.0-rc.1-sucio") is None


def test_a_candidate_moves_to_the_next_candidate_and_to_the_final() -> None:
    running = ReleaseVersion.parse("v1.4.0-rc.1")

    assert decide(running, _manifest(version="v1.4.0-rc.2"), NOW).state is UpdateState.RECOMMENDED
    assert decide(running, _manifest(version="v1.4.0"), NOW).state is UpdateState.RECOMMENDED


def test_a_candidate_is_never_offered_a_downgrade() -> None:
    final = ReleaseVersion.parse("v1.4.0")
    second = ReleaseVersion.parse("v1.4.0-rc.2")

    assert decide(final, _manifest(version="v1.4.0-rc.2"), NOW).state is UpdateState.UP_TO_DATE
    assert decide(second, _manifest(version="v1.4.0-rc.2"), NOW).state is UpdateState.UP_TO_DATE
    assert decide(second, _manifest(version="v1.4.0-rc.1"), NOW).state is UpdateState.UP_TO_DATE


def test_a_candidate_can_be_the_required_minimum() -> None:
    running = ReleaseVersion.parse("v1.4.0-rc.1")
    manifest = _manifest(version="v1.4.0-rc.2", min_version="v1.4.0-rc.2")

    assert decide(running, manifest, NOW).state is UpdateState.REQUIRED
