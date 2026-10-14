"""Migración `e5b9c2a7d314` (cloud_link + índices keyset) sobre SQLite real:
`upgrade head` desde el head anterior, restricción de fila única y
`downgrade -1`."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.infrastructure.config.settings import get_settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.bootstrap import (
    _REGISTERED_MODELS,  # pyright: ignore[reportPrivateUsage]
)
from app.paths import resource_dir

PREVIOUS_HEAD = "c3a7d1e9f5b2"
THIS_REVISION = "e5b9c2a7d314"
NEW_TABLES = {"cloud_link", "cloud_sync_watermarks"}
NEW_INDEXES = {
    "messages": "ix_messages_created_at_id",
    "conversations": "ix_conversations_created_at_id",
    "refresh_token": "ix_refresh_token_created_at_jti",
    "audit_query": "ix_audit_query_created_at_id",
}


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


def _version(db: Path) -> str | None:
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def _tables(db: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _index_names(db: Path, table: str) -> set[str]:
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        return {str(ix["name"]) for ix in inspect(engine).get_indexes(table)}
    finally:
        engine.dispose()


def _pre_migration_database(db: Path) -> None:
    """Una instalación en el head anterior: sin las tablas ni los índices."""
    assert len(_REGISTERED_MODELS) > 0  # los modelos registran sus tablas en el metadata
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            for index in NEW_INDEXES.values():
                conn.execute(text(f"DROP INDEX {index}"))
            for table in sorted(NEW_TABLES):
                conn.execute(text(f"DROP TABLE {table}"))
    finally:
        engine.dispose()


def test_upgrade_creates_tables_and_indexes_and_downgrade_removes_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "migracion.db"
    monkeypatch.setenv("AGENT_DB_ENGINE", "sqlite")
    monkeypatch.setenv("AGENT_DB_PATH", str(db))
    _pre_migration_database(db)
    command.stamp(_config(), PREVIOUS_HEAD)
    assert NEW_TABLES.isdisjoint(_tables(db))

    command.upgrade(_config(), THIS_REVISION)

    assert _version(db) == THIS_REVISION
    assert _tables(db) >= NEW_TABLES
    for table, index in NEW_INDEXES.items():
        assert index in _index_names(db, table)

    # Fila única: `CHECK (id = 1)`.
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        insert = text(
            "INSERT INTO cloud_link (id, cloud_url, pseudonym_key_encrypted, install_id, status,"
            " notices, consecutive_failures) VALUES (:id, '', 'k', 'abc', 'unlinked', '[]', 0)"
        )
        with engine.begin() as conn:
            conn.execute(insert, {"id": 1})
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(insert, {"id": 2})
    finally:
        engine.dispose()

    command.downgrade(_config(), "-1")

    assert _version(db) == PREVIOUS_HEAD
    assert NEW_TABLES.isdisjoint(_tables(db))
    for table, index in NEW_INDEXES.items():
        assert index not in _index_names(db, table)

    # Idempotente: volver a subir deja el mismo resultado.
    command.upgrade(_config(), THIS_REVISION)
    assert _version(db) == THIS_REVISION
    assert _tables(db) >= NEW_TABLES


def test_upgrade_is_a_noop_when_the_objects_already_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una BD SQLite nueva nace del metadata y se sella en `head`; si después
    se sella atrás y se sube, la migración no debe chocar con lo que existe."""
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
    assert _tables(db) >= NEW_TABLES
