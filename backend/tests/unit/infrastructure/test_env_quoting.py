"""El instalador escribe los valores del `.env` entre comillas simples.

`EnvQuote` (Pascal, `installer/savi.iss`) y `quote_env_value`
(`app/launcher.py`) aplican la misma regla; el Pascal se verificó compilando
y corriendo el bloque real contra esta matriz. Acá se fija la regla del lado
Python y que `dotenv_values` —lo que usa pydantic-settings— lee todo de
vuelta idéntico.
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from dotenv import dotenv_values

from app.infrastructure.config.settings import Settings
from app.launcher import quote_env_value

_MATRIX = [
    "pass #word",
    "${A}x",
    "  lead  ",
    '"quoted"',
    "'x",
    '"a"b',
    "a\\b\\\\c",
    "C:\\Program Files\\Git\\bin\\bash.exe",
    "ñandú€",
    "100%",
    "",
    "a$${B}c${",
    "x\\",
    "it's \\' ${",
]


@pytest.mark.parametrize("value", _MATRIX)
def test_quoted_value_round_trips_through_dotenv(value: str) -> None:
    parsed = dotenv_values(stream=io.StringIO(f"K={quote_env_value(value)}\n"))

    assert parsed["K"] == value


def test_interpolation_does_not_leak_a_defined_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A", "filtrada")

    parsed = dotenv_values(stream=io.StringIO(f"K={quote_env_value('${A}x')}\n"))

    assert parsed["K"] == "${A}x"


def test_pydantic_settings_reads_the_quoted_env_file(tmp_path: Path) -> None:
    """Es el camino real: un .env UTF-8 sin BOM leído por `Settings`."""
    password = "pa ss #${X}'\"\\ñ€"
    env = tmp_path / ".env"
    env.write_bytes(f"ERP_DB_PASSWORD={quote_env_value(password)}\r\n".encode())

    previous = os.environ.pop("ERP_DB_PASSWORD", None)
    try:
        settings = Settings(_env_file=env)  # type: ignore[call-arg]
    finally:
        if previous is not None:
            os.environ["ERP_DB_PASSWORD"] = previous

    assert settings.erp_db_password == password


def _fernet_key_like_the_installer(raw: bytes) -> str:
    """Port de `Base64UrlEncode` de savi.iss: alfabeto URL-safe con relleno."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    out = ""
    for i in range(0, len(raw), 3):
        chunk = raw[i : i + 3]
        b0, b1, b2 = (list(chunk) + [0, 0])[:3]
        triple = b0 * 65536 + b1 * 256 + b2
        out += alphabet[(triple // 262144) % 64] + alphabet[(triple // 4096) % 64]
        out += alphabet[(triple // 64) % 64] if len(chunk) > 1 else "="
        out += alphabet[triple % 64] if len(chunk) > 2 else "="
    return out


def test_installer_base64url_matches_the_standard_library() -> None:
    for size in (1, 2, 3, 32, 48):
        raw = os.urandom(size)
        assert _fernet_key_like_the_installer(raw) == base64.urlsafe_b64encode(raw).decode()


def test_fernet_key_built_with_the_installer_rule_is_accepted() -> None:
    key = _fernet_key_like_the_installer(os.urandom(32))

    assert len(key) == 44
    assert key.endswith("=")
    Fernet(key.encode())  # no levanta
