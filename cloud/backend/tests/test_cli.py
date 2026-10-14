"""`cloud-admin` sobre SQLite. Sincrónicos: el CLI crea su propio event loop."""

from __future__ import annotations

import re

import pytest

from app.cli import main
from app.shared.tokens import hash_secret


@pytest.fixture(autouse=True)
def _env(sqlite_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_DATABASE_URL", sqlite_url)


def test_client_create_and_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["client", "create", "--code", "FARMX", "--name", "Farmacias X"]) == 0
    assert "FARMX" in capsys.readouterr().out
    assert main(["client", "list"]) == 0
    out = capsys.readouterr().out
    assert "FARMX" in out and "Farmacias X" in out and "active" in out


def test_client_create_rejects_invalid_and_duplicate_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["client", "create", "--code", "farmx", "--name", "x"]) == 1
    assert "invalid_client_code" in capsys.readouterr().err
    assert main(["client", "create", "--code", "FARMX", "--name", "Uno"]) == 0
    assert main(["client", "create", "--code", "FARMX", "--name", "Dos"]) == 1
    assert "client_code_already_exists" in capsys.readouterr().err


def test_token_create_prints_token_once_list_and_revoke(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["client", "create", "--code", "FARMX", "--name", "Farmacias X"])
    capsys.readouterr()

    assert main(["token", "create", "--client", "FARMX", "--expires-hours", "24"]) == 0
    captured = capsys.readouterr()
    token = captured.out.strip()
    assert re.fullmatch(r"svk_enr_[0-9A-Za-z]{43}", token)  # stdout = solo el token
    token_id = re.search(r"Token ([0-9a-f-]{36})", captured.err)
    assert token_id is not None

    assert main(["token", "list", "--client", "FARMX"]) == 0
    listing = capsys.readouterr().out
    assert token_id.group(1) in listing and "pending" in listing
    assert token not in listing and hash_secret(token).hex() not in listing

    assert main(["token", "revoke", token_id.group(1)]) == 0
    capsys.readouterr()
    main(["token", "list", "--client", "FARMX"])
    assert "revoked" in capsys.readouterr().out


def test_token_create_unknown_client(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["token", "create", "--client", "NOPE"]) == 1
    assert "client_not_found" in capsys.readouterr().err


def test_instance_list_empty(capsys: pytest.CaptureFixture[str]) -> None:
    main(["client", "create", "--code", "FARMX", "--name", "Farmacias X"])
    capsys.readouterr()
    assert main(["instance", "list", "--client", "FARMX"]) == 0
    assert "NAME" in capsys.readouterr().out


def test_missing_database_url_is_a_config_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: pytest.TempPathFactory,
) -> None:
    monkeypatch.delenv("CLOUD_DATABASE_URL")
    monkeypatch.chdir(str(tmp_path))  # sin .env cercano
    assert main(["client", "list"]) == 2
    assert "CLOUD_DATABASE_URL" in capsys.readouterr().err
