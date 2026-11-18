"""`ensure_schema(settings)` migra la base de ESOS settings, no la del `.env`.

Antes `alembic/env.py` volvía a leer `get_settings()`: una prueba que pasaba una
base SQLite temporal terminaba migrando la base real del agente del equipo.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import app.infrastructure.config as config_module
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.bootstrap import ensure_schema


def _settings(db_path: Path) -> Settings:
    return Settings(
        agent_db_engine="sqlite",
        agent_db_path=str(db_path),
        erp_db_host="localhost",
        erp_db_port=5432,
        erp_db_user="u",
        erp_db_password="p",
        erp_db_name="erp",
        jwt_secret="x" * 32,
    )


def test_the_migration_never_reads_the_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def must_not_be_called() -> Settings:
        raise AssertionError("ensure_schema leyó la base del .env")

    monkeypatch.setattr(config_module, "get_settings", must_not_be_called)
    db_path = tmp_path / "agente.db"

    ensure_schema(_settings(db_path))  # base nueva: create_all + stamp
    ensure_schema(_settings(db_path))  # base existente: upgrade

    with sqlite3.connect(db_path) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert version is not None
