"""URL de la BD del agente, placeholders del instalador y clave Fernet."""

from __future__ import annotations

import socket

import pytest
from alembic.config import Config
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.infrastructure.config.settings import INSTALLER_PLACEHOLDER, Settings
from app.launcher import _port_is_free

_PASSWORD = "p@ss:w/rd%40#?"


def _pg(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "agent_db_engine": "postgresql",
        "agent_db_host": "db.local",
        "agent_db_port": 5433,
        "agent_db_user": "us@er:x",
        "agent_db_password": _PASSWORD,
        "agent_db_name": "savi",
        "jwt_secret": "un-secreto-generado-de-verdad",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_agent_db_url_round_trips_special_characters() -> None:
    url = make_url(_pg().agent_db_url)

    assert url.password == _PASSWORD
    assert url.username == "us@er:x"
    assert (url.host, url.port, url.database) == ("db.local", 5433, "savi")


def test_alembic_option_accepts_a_percent_in_the_url() -> None:
    """`set_main_option` interpola `%`; env.py lo duplica."""
    rendered = _pg().agent_db_url
    config = Config()

    config.set_main_option("sqlalchemy.url", rendered.replace("%", "%%"))

    assert config.get_main_option("sqlalchemy.url") == rendered


def test_alembic_option_without_escaping_would_fail() -> None:
    with pytest.raises(ValueError):
        Config().set_main_option("sqlalchemy.url", _pg().agent_db_url)


@pytest.mark.parametrize("env", ["production", "staging"])
def test_installer_placeholder_jwt_secret_is_rejected(env: str) -> None:
    with pytest.raises(ValidationError, match="Volver a configurar"):
        _pg(app_env=env, jwt_secret=INSTALLER_PLACEHOLDER)


def test_installer_placeholder_jwt_secret_is_allowed_in_development() -> None:
    assert _pg(app_env="development", jwt_secret=INSTALLER_PLACEHOLDER)


def test_invalid_credentials_key_is_rejected_with_a_clear_message() -> None:
    with pytest.raises(ValidationError, match="ERP_CREDENTIALS_KEY.*Volver a configurar"):
        _pg(erp_credentials_key=INSTALLER_PLACEHOLDER)


def test_invalid_old_credentials_key_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ERP_CREDENTIALS_KEY_OLD"):
        _pg(erp_credentials_key_old="basura")


def test_valid_and_empty_credentials_keys_are_accepted() -> None:
    assert _pg(erp_credentials_key=Fernet.generate_key().decode())
    assert _pg(erp_credentials_key="")


def test_a_bound_but_not_listening_port_is_not_free() -> None:
    """`connect_ex` lo daba por libre: nadie escuchaba, pero `bind` falla."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        assert not _port_is_free("127.0.0.1", taken.getsockname()[1])


def test_a_port_that_cannot_be_bound_is_not_free(monkeypatch: pytest.MonkeyPatch) -> None:
    """WinError 10013: rango excluido por Hyper-V/WSL/Docker."""

    def refuse(self: socket.socket, address: object) -> None:
        raise PermissionError(10013, "acceso denegado")

    monkeypatch.setattr(socket.socket, "bind", refuse)

    assert not _port_is_free("127.0.0.1", 8000)
