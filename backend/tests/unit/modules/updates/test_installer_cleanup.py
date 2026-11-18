"""El instalador descargado se borra aunque siga bloqueado al cerrar el intento."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.updates.infrastructure import provider


def _fail_then_succeed(monkeypatch: pytest.MonkeyPatch, failures: int) -> list[int]:
    calls: list[int] = []

    def delete(_directory: Path) -> None:
        calls.append(1)
        if len(calls) <= failures:
            raise PermissionError("en uso")

    monkeypatch.setattr(provider, "delete_downloaded_installers", delete)
    monkeypatch.setattr(provider, "data_dir", lambda: Path("."))
    return calls


async def test_retries_until_the_installer_is_free(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fail_then_succeed(monkeypatch, failures=2)

    await provider._delete_installer_when_free((0.0, 0.0, 0.0, 0.0))

    assert len(calls) == 3


async def test_gives_up_and_warns_after_the_last_retry(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls = _fail_then_succeed(monkeypatch, failures=99)

    await provider._delete_installer_when_free((0.0, 0.0))

    assert len(calls) == 2
    assert "no se pudo borrar el instalador" in caplog.text
