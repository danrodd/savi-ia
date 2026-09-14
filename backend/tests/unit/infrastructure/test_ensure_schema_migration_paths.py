"""`ensure_schema()` en sus dos caminos reales de SQLite.

`bootstrap.py` documenta que una instalación de escritorio nueva NO
reproduce el historial completo de migraciones (varias no son portables
a SQLite: `now()` de Postgres, `postgresql.JSONB`) — arma el esquema
desde el metadata y sella con `stamp head`. Lo confirmé a mano: correr
`alembic upgrade` desde cero sobre SQLite falla en `a43047be72dd` con
`UnsupportedCompilationError: ... JSONB`.

Eso significa que el camino que SÍ hay que probar de verdad es el otro:
una instalación EXISTENTE, que ya tiene esquema y datos de antes de la
migración `d1a4c8f0e921`, recibe `command.upgrade(head)` cuando arranca
de nuevo. Los tests de índices parciales de `test_repository_and_seed.py`
arman el esquema con `create_all` directo — nunca pasan por
`ensure_schema()` ni por el `upgrade()` real de una migración. Este
archivo cierra ese hueco.

Nota de plomería: `alembic/env.py` lee `get_settings()` (el singleton
cacheado del proceso), no el objeto `Settings` que recibe
`ensure_schema()` como parámetro. Hay que sincronizar los dos con las
mismas variables de entorno y limpiar el cache antes y después de cada
test, o un test deja el cache apuntando a un `tmp_path` que ya no
existe y rompe el resto de la suite.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.database.bootstrap import ensure_schema
from app.paths import resource_dir


def _alembic_config() -> Config:
    """Igual que `bootstrap._alembic_config` (privada): se duplica acá en
    vez de importarla para no ensanchar la API de un módulo interno solo
    para un test."""
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


def _settings_for(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    # `ensure_schema()` usa el objeto que recibe; `alembic/env.py` usa
    # `get_settings()` — sincronizados con las mismas variables.
    monkeypatch.setenv("AGENT_DB_ENGINE", "sqlite")
    monkeypatch.setenv("AGENT_DB_PATH", str(db_path))
    return Settings(agent_db_engine="sqlite", agent_db_path=str(db_path))


def _table_columns(db_path: Path, table: str) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        return {str(c["name"]) for c in inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def _index_names(db_path: Path, table: str) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        return {str(ix["name"]) for ix in inspect(engine).get_indexes(table)}
    finally:
        engine.dispose()


def test_fresh_sqlite_gets_the_current_schema_via_create_all_and_stamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Instalación nueva: el archivo no existe todavía."""
    db_path = tmp_path / "fresh.db"
    settings = _settings_for(db_path, monkeypatch)

    ensure_schema(settings)

    columns = _table_columns(db_path, "conversations")
    assert {"erp_database_id", "owner_erp_database_id"}.issubset(columns)
    assert "ix_conversations_owner" in _index_names(db_path, "conversations")

    llm_columns = _table_columns(db_path, "llm_provider_configs")
    assert {"provider", "credential_encrypted", "is_active"}.issubset(llm_columns)
    assert "uq_llm_provider_configs_active" in _index_names(
        db_path, "llm_provider_configs"
    )

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()
    assert version == "e7b2d9a4c613"


def test_existing_sqlite_upgrades_and_backfills_the_owner_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Instalación real ya en uso: tiene esquema y datos de ANTES de
    `d1a4c8f0e921` (sin `owner_erp_database_id`). El arranque siguiente
    tiene que traerla a `head` sin perder la conversación existente, y
    backfillear la identidad desde la base consultada — antes de D10 eran
    siempre la misma base, así que copiar es exactamente correcto.
    """
    db_path = tmp_path / "existing.db"
    settings = _settings_for(db_path, monkeypatch)
    queried_database_id = str(uuid4())
    conversation_id = str(uuid4())

    # Arma el esquema EXACTO de la revisión c93e5a1d7f42 (la anterior a la
    # mía) a mano: no se puede reproducir corriendo las migraciones desde
    # cero en SQLite (ver el docstring del módulo), así que se declara el
    # DDL tal cual quedó esa revisión para `conversations`.
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE erp_databases (
                        id VARCHAR(36) PRIMARY KEY,
                        code VARCHAR(32) NOT NULL,
                        name VARCHAR(120) NOT NULL,
                        host VARCHAR(255) NOT NULL,
                        port INTEGER NOT NULL,
                        database VARCHAR(120) NOT NULL,
                        username VARCHAR(120) NOT NULL,
                        password_encrypted TEXT NOT NULL,
                        statement_timeout_ms INTEGER NOT NULL,
                        is_default BOOLEAN NOT NULL,
                        is_active BOOLEAN NOT NULL,
                        deleted_at DATETIME,
                        credentials_unreadable BOOLEAN NOT NULL,
                        last_connection_ok_at DATETIME,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE conversations (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INTEGER,
                        erp_database_id VARCHAR(36),
                        title VARCHAR(200) NOT NULL,
                        title_locked BOOLEAN NOT NULL DEFAULT 0,
                        created_at DATETIME,
                        updated_at DATETIME,
                        deleted_at DATETIME
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "INSERT INTO erp_databases (id, code, name, host, port, database, "
                    "username, password_encrypted, statement_timeout_ms, is_default, "
                    "is_active, credentials_unreadable) VALUES "
                    "(:id, 'NORTE', 'Cliente Norte', 'localhost', 5432, 'erp_norte', "
                    "'postgres', 'cifrado', 60000, 1, 1, 0)"
                ),
                {"id": queried_database_id},
            )
            conn.execute(
                text(
                    "INSERT INTO conversations (id, user_id, erp_database_id, title, "
                    "title_locked) VALUES (:id, 7, :db_id, 'Hilo anterior a D10', 0)"
                ),
                {"id": conversation_id, "db_id": queried_database_id},
            )
    finally:
        engine.dispose()

    # `command.stamp` crea `alembic_version` si no existe. Al sellarla en
    # la revisión anterior, `ensure_schema()` verá `conversations` ya
    # creada (no está "fresca") y tomará el camino `upgrade`, no `stamp`.
    command.stamp(_alembic_config(), "c93e5a1d7f42")

    get_settings.cache_clear()
    ensure_schema(settings)

    columns = _table_columns(db_path, "conversations")
    assert "owner_erp_database_id" in columns
    assert "ix_conversations_owner" in _index_names(db_path, "conversations")

    llm_columns = _table_columns(db_path, "llm_provider_configs")
    assert {"provider", "credential_encrypted", "is_active"}.issubset(llm_columns)
    assert "uq_llm_provider_configs_active" in _index_names(
        db_path, "llm_provider_configs"
    )

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT title, erp_database_id, owner_erp_database_id "
                    "FROM conversations WHERE id=:id"
                ),
                {"id": conversation_id},
            ).one()
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()

    # La conversación sobrevive la recreación de tabla (modo batch) con su
    # contenido intacto...
    assert row.title == "Hilo anterior a D10"
    assert row.erp_database_id == queried_database_id
    # ...y la identidad se backfillea desde la base consultada.
    assert row.owner_erp_database_id == queried_database_id
    assert version == "e7b2d9a4c613"
