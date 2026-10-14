"""Migración `f1a6c3d8e2b4` (tabla `user_totp`) sobre SQLite real: subir, bajar y volver a subir."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.infrastructure.config.settings import get_settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.bootstrap import (
    _REGISTERED_MODELS,  # pyright: ignore[reportPrivateUsage]
)
from app.paths import resource_dir

PREVIOUS_HEAD = "e5b9c2a7d314"
THIS_REVISION = "f1a6c3d8e2b4"


def _config() -> Config:
    root = resource_dir()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(autouse=True)
def _isolated_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _tables(db: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _version(db: Path) -> str | None:
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def _database_before(db: Path) -> None:
    """Una instalación en el head anterior: todo el esquema, sin `user_totp`."""
    assert len(_REGISTERED_MODELS) > 0
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE user_totp"))
    finally:
        engine.dispose()


def test_upgrade_creates_the_table_and_downgrade_removes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "totp.db"
    monkeypatch.setenv("AGENT_DB_ENGINE", "sqlite")
    monkeypatch.setenv("AGENT_DB_PATH", str(db))
    _database_before(db)
    command.stamp(_config(), PREVIOUS_HEAD)
    assert "user_totp" not in _tables(db)

    command.upgrade(_config(), THIS_REVISION)

    assert _version(db) == THIS_REVISION
    assert "user_totp" in _tables(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("user_totp")}
        # La identidad es (base, usuario): el `idUsuario` se repite entre clientes.
        assert {
            "erp_database_id",
            "user_id",
            "secret_encrypted",
            "enabled_at",
            "last_step",
        } <= columns
        keys = inspect(engine).get_pk_constraint("user_totp")["constrained_columns"]
        assert set(keys) == {"erp_database_id", "user_id"}
    finally:
        engine.dispose()

    command.downgrade(_config(), "-1")
    assert _version(db) == PREVIOUS_HEAD
    assert "user_totp" not in _tables(db)

    command.upgrade(_config(), THIS_REVISION)
    assert "user_totp" in _tables(db)


def test_upgrade_is_a_noop_when_the_table_already_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una BD SQLite nueva nace del metadata y se sella en `head`."""
    db = tmp_path / "ya_existe.db"
    monkeypatch.setenv("AGENT_DB_ENGINE", "sqlite")
    monkeypatch.setenv("AGENT_DB_PATH", str(db))
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    command.stamp(_config(), PREVIOUS_HEAD)

    command.upgrade(_config(), THIS_REVISION)

    assert _version(db) == THIS_REVISION
    assert "user_totp" in _tables(db)
