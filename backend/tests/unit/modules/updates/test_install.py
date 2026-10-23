"""Resultado de un intento de instalación: cómo se decide y qué se le dice a la persona."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.modules.updates.application.install_history import reconcile_last_install
from app.modules.updates.domain.exceptions import InvalidInstallResultError
from app.modules.updates.domain.interfaces import InstallResultReader
from app.modules.updates.domain.value_objects import (
    HISTORY_LIMIT,
    InstallOutcome,
    InstallRecord,
    InstallResult,
    ReleaseVersion,
    WatcherStep,
    exit_reason,
    settle,
)
from app.modules.updates.infrastructure.install_files import (
    FileInstallHistory,
    FileInstallResultReader,
    delete_downloaded_installers,
    prune_install_logs,
)

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
OLD = ReleaseVersion.parse("v1.3.2")
NEW = ReleaseVersion.parse("v1.4.0")


def _result(
    step: WatcherStep, *, exit_code: int | None = None, attempt: str = "a1"
) -> InstallResult:
    return InstallResult(
        attempt_id=attempt,
        from_version=OLD,
        to_version=NEW,
        started_at=NOW,
        step=step,
        exit_code=exit_code,
        finished_at=None if step is WatcherStep.STARTED else NOW,
    )


def _record(
    attempt: str = "a1", outcome: InstallOutcome = InstallOutcome.INSTALLED
) -> InstallRecord:
    return InstallRecord(
        attempt_id=attempt,
        from_version=OLD,
        to_version=NEW,
        started_at=NOW,
        finished_at=NOW,
        outcome=outcome,
    )


# ------------------------------------------------------------------- settle


@pytest.mark.parametrize(
    ("step", "exit_code", "running", "expected"),
    [
        # Lo que corre ahora manda: si es la versión nueva, se instaló.
        (WatcherStep.FINISHED, 0, NEW, InstallOutcome.INSTALLED),
        (WatcherStep.FINISHED, None, NEW, InstallOutcome.INSTALLED),
        (WatcherStep.STARTED, None, NEW, InstallOutcome.INSTALLED),
        (WatcherStep.FINISHED, 0, OLD, InstallOutcome.ROLLED_BACK),
        (WatcherStep.FAILED, 4, OLD, InstallOutcome.FAILED),
        (WatcherStep.FAILED, None, OLD, InstallOutcome.FAILED),
        (WatcherStep.TIMEOUT, None, OLD, InstallOutcome.TIMEOUT),
        (WatcherStep.CANCELLED, None, OLD, InstallOutcome.CANCELLED),
        (WatcherStep.STARTED, None, OLD, InstallOutcome.INTERRUPTED),
    ],
)
def test_settle_decides_by_the_version_that_is_running(
    step: WatcherStep, exit_code: int | None, running: ReleaseVersion, expected: InstallOutcome
) -> None:
    record = settle(_result(step, exit_code=exit_code), running, NOW)

    assert record.outcome is expected


def test_settle_uses_now_when_the_watcher_never_wrote_an_end() -> None:
    later = datetime(2026, 11, 2, 16, 0, tzinfo=UTC)

    assert settle(_result(WatcherStep.STARTED), OLD, later).finished_at == later


# ----------------------------------------------------------------- mensajes


def test_every_outcome_has_a_complete_message() -> None:
    for outcome in InstallOutcome:
        message = _record(outcome=outcome).message
        assert message.endswith(".")
        assert "v1.4.0" in message or "v1.3.2" in message


def test_a_failed_message_names_the_reason_and_the_version_that_remains() -> None:
    record = InstallRecord(
        attempt_id="a1",
        from_version=OLD,
        to_version=NEW,
        started_at=NOW,
        finished_at=NOW,
        outcome=InstallOutcome.FAILED,
        exit_code=8,
    )

    assert record.message == (
        "La actualización a v1.4.0 no se completó: la instalación necesita reiniciar el equipo. "
        "SAVI sigue en v1.3.2."
    )


@pytest.mark.parametrize("code", [1, 2, 3, 4, 5, 6, 7, 8])
def test_each_documented_inno_exit_code_has_its_own_reason(code: int) -> None:
    assert "código" not in exit_reason(code)


def test_unknown_exit_codes_are_reported_with_the_code() -> None:
    assert exit_reason(99) == "la instalación terminó con un error (código 99)"
    assert exit_reason(None) == "no se pudo iniciar el instalador"


# ----------------------------------------------------------- forma del archivo


def _payload(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "attempt_id": "a1",
        "from_version": "v1.3.2",
        "to_version": "v1.4.0",
        "started_at": "2026-11-02T15:00:00Z",
        "step": "failed",
        "exit_code": 4,
        "finished_at": "2026-11-02T15:01:00Z",
        "relaunched": True,
        "running_version": "v1.3.2",
    }
    data.update(overrides)
    return data


def test_result_reads_what_the_watcher_writes() -> None:
    result = InstallResult.from_mapping(_payload())

    assert result.step is WatcherStep.FAILED
    assert result.exit_code == 4
    assert result.relaunched is True
    assert result.to_version == NEW


def test_result_accepts_the_nulls_the_watcher_writes_while_it_is_running() -> None:
    result = InstallResult.from_mapping(
        _payload(step="started", exit_code=None, finished_at=None, running_version=None)
    )

    assert result.exit_code is None
    assert result.finished_at is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"attempt_id": ""},
        {"to_version": "1.4"},
        {"step": "explotó"},
        {"started_at": "ayer"},
        {"started_at": "2026-11-02T15:00:00"},
        {"exit_code": "4"},
        {"exit_code": True},
    ],
)
def test_result_rejects_malformed_files(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidInstallResultError):
        InstallResult.from_mapping(_payload(**overrides))


def test_result_rejects_something_that_is_not_an_object() -> None:
    with pytest.raises(InvalidInstallResultError):
        InstallResult.from_mapping(["no", "es", "un", "objeto"])


def test_a_record_survives_a_round_trip() -> None:
    record = _record(outcome=InstallOutcome.FAILED)

    assert InstallRecord.from_mapping(record.to_mapping()) == record


# --------------------------------------------------------------- archivos reales


def test_reader_returns_none_when_there_is_no_file(tmp_path: Path) -> None:
    assert FileInstallResultReader(tmp_path / "last-install.json").read() is None


def test_reader_reads_the_watcher_file(tmp_path: Path) -> None:
    path = tmp_path / "last-install.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    result = FileInstallResultReader(path).read()

    assert result is not None
    assert result.attempt_id == "a1"


@pytest.mark.parametrize("content", ["", "{", "[]", '{"attempt_id": "a1"}'])
def test_reader_ignores_an_unreadable_file(tmp_path: Path, content: str) -> None:
    path = tmp_path / "last-install.json"
    path.write_text(content, encoding="utf-8")

    assert FileInstallResultReader(path).read() is None


def test_history_lists_the_newest_first(tmp_path: Path) -> None:
    history = FileInstallHistory(tmp_path / "history.jsonl")
    for attempt in ("a1", "a2", "a3"):
        history.append(_record(attempt))

    assert [record.attempt_id for record in history.recent(10)] == ["a3", "a2", "a1"]
    assert [record.attempt_id for record in history.recent(1)] == ["a3"]


def test_history_keeps_only_the_latest_entries(tmp_path: Path) -> None:
    history = FileInstallHistory(tmp_path / "history.jsonl")
    for number in range(HISTORY_LIMIT + 5):
        history.append(_record(f"a{number}"))

    recent = history.recent(HISTORY_LIMIT + 10)
    assert len(recent) == HISTORY_LIMIT
    assert recent[0].attempt_id == f"a{HISTORY_LIMIT + 4}"
    assert recent[-1].attempt_id == "a5"


def test_history_skips_a_corrupt_line_and_keeps_the_rest(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    history = FileInstallHistory(path)
    history.append(_record("a1"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write("esto no es json\n")
    history.append(_record("a2"))

    assert [record.attempt_id for record in history.recent(10)] == ["a2", "a1"]


def test_history_is_empty_without_a_file(tmp_path: Path) -> None:
    assert FileInstallHistory(tmp_path / "history.jsonl").recent(5) == []


def test_old_install_logs_are_pruned_keeping_the_newest(tmp_path: Path) -> None:
    for number in range(8):
        log = tmp_path / f"install-{number}.log"
        log.write_text("x", encoding="utf-8")
        timestamp = 1_700_000_000 + number
        os.utime(log, (timestamp, timestamp))

    prune_install_logs(tmp_path, keep=3)

    assert sorted(path.name for path in tmp_path.glob("install-*.log")) == [
        "install-5.log",
        "install-6.log",
        "install-7.log",
    ]


def test_downloaded_installers_are_deleted_but_other_files_stay(tmp_path: Path) -> None:
    (tmp_path / "SAVI-Setup-v1.4.0.exe").write_bytes(b"MZ")
    (tmp_path / "SAVI-Setup-v1.4.0.exe.partial").write_bytes(b"MZ")
    (tmp_path / "history.jsonl").write_text("", encoding="utf-8")

    delete_downloaded_installers(tmp_path)

    assert [path.name for path in tmp_path.iterdir()] == ["history.jsonl"]


# ---------------------------------------------------------------- reconciliación


class _Reader(InstallResultReader):
    def __init__(self, result: InstallResult | None) -> None:
        self.result = result

    def read(self) -> InstallResult | None:
        return self.result


def test_reconcile_adds_a_pending_attempt_once(tmp_path: Path) -> None:
    history = FileInstallHistory(tmp_path / "history.jsonl")
    reader = _Reader(_result(WatcherStep.FINISHED, exit_code=0))

    first = reconcile_last_install(results=reader, history=history, running=NEW, now=NOW)
    second = reconcile_last_install(results=reader, history=history, running=NEW, now=NOW)

    assert first is not None
    assert first.outcome is InstallOutcome.INSTALLED
    assert second is None
    assert len(history.recent(10)) == 1


def test_reconcile_does_nothing_without_a_result(tmp_path: Path) -> None:
    history = FileInstallHistory(tmp_path / "history.jsonl")

    assert (
        reconcile_last_install(results=_Reader(None), history=history, running=OLD, now=NOW) is None
    )
    assert history.recent(10) == []


def test_reconcile_records_a_new_attempt_after_an_old_one(tmp_path: Path) -> None:
    history = FileInstallHistory(tmp_path / "history.jsonl")
    history.append(_record("a1", InstallOutcome.CANCELLED))
    reader = _Reader(_result(WatcherStep.FAILED, exit_code=4, attempt="a2"))

    record = reconcile_last_install(results=reader, history=history, running=OLD, now=NOW)

    assert record is not None
    assert record.attempt_id == "a2"
    assert [item.attempt_id for item in history.recent(10)] == ["a2", "a1"]
