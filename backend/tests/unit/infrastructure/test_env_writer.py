"""El `.env` del instalador lleva las contraseñas de las dos bases de datos.

`--login` lo edita para guardar el token de Claude, así que un bug acá no
rompe el login: rompe la conexión al ERP del cliente.
"""

from __future__ import annotations

from app.launcher import replace_env_line

KEY = "CLAUDE_CODE_OAUTH_TOKEN"


def test_replaces_existing_key_in_place() -> None:
    lines = ["APP_PORT=8000\n", f"{KEY}=viejo\n", "ERP_DB_PASSWORD=secreta\n"]

    result = replace_env_line(lines, KEY, "nuevo")

    assert result == ["APP_PORT=8000\n", f"{KEY}=nuevo\n", "ERP_DB_PASSWORD=secreta\n"]


def test_replaces_commented_key() -> None:
    """La plantilla deja la clave comentada cuando no se cargó ningún token."""
    lines = ["APP_PORT=8000\n", f"# {KEY}=\n"]

    assert replace_env_line(lines, KEY, "tok") == ["APP_PORT=8000\n", f"{KEY}=tok\n"]


def test_appends_when_key_is_absent() -> None:
    lines = ["APP_PORT=8000\n"]

    assert replace_env_line(lines, KEY, "tok") == ["APP_PORT=8000\n", f"{KEY}=tok\n"]


def test_appends_newline_before_when_file_lacks_trailing_one() -> None:
    """Sin esto la clave nueva se pega a la última y se pierden las dos."""
    lines = ["APP_PORT=8000"]

    assert replace_env_line(lines, KEY, "tok") == ["APP_PORT=8000\n", f"{KEY}=tok\n"]


def test_preserves_crlf() -> None:
    """El instalador escribe el .env desde Inno; en Windows eso es CRLF."""
    lines = [f"{KEY}=viejo\r\n", "APP_PORT=8000\r\n"]

    assert replace_env_line(lines, KEY, "nuevo") == [f"{KEY}=nuevo\r\n", "APP_PORT=8000\r\n"]


def test_replaces_only_the_first_occurrence() -> None:
    """Un .env con la clave duplicada no debe quedar con dos valores nuevos."""
    lines = [f"{KEY}=a\n", f"{KEY}=b\n"]

    assert replace_env_line(lines, KEY, "c") == [f"{KEY}=c\n", f"{KEY}=b\n"]


def test_does_not_touch_a_key_that_merely_shares_a_prefix() -> None:
    lines = [f"{KEY}_BACKUP=otro\n"]

    result = replace_env_line(lines, KEY, "tok")

    assert result == [f"{KEY}_BACKUP=otro\n", f"{KEY}=tok\n"]
