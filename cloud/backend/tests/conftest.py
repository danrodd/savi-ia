from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.models import Base


def _pg_settings() -> dict[str, str]:
    # Credenciales SOLO por entorno: nunca van en el repo. Sin CLOUD_TEST_PG_PASSWORD los
    # tests contra Postgres se saltan.
    return {
        "host": os.environ.get("CLOUD_TEST_PG_HOST", "localhost"),
        "port": os.environ.get("CLOUD_TEST_PG_PORT", "5432"),
        "user": os.environ.get("CLOUD_TEST_PG_USER", "postgres"),
        "password": os.environ.get("CLOUD_TEST_PG_PASSWORD", ""),
    }


def _admin_url() -> str:
    cfg = _pg_settings()
    return (
        f"postgresql+asyncpg://{quote(cfg['user'])}:{quote(cfg['password'])}"
        f"@{cfg['host']}:{cfg['port']}/postgres"
    )


async def _admin_execute(statement: str | None) -> None:
    """Ejecuta una sentencia DDL fuera de transacción (o solo sondea si es None)."""
    engine = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text(statement or "SELECT 1"))
    finally:
        await engine.dispose()


def _postgres_available() -> bool:
    if not _pg_settings()["password"]:
        return False
    try:
        asyncio.run(asyncio.wait_for(_admin_execute(None), timeout=5))
    except Exception:  # noqa: BLE001
        return False
    return True


@contextmanager
def temporary_postgres() -> Generator[str]:
    """Crea una base desechable y entrega su URL asyncpg; la borra al salir."""
    if not _postgres_available():
        pytest.skip("Sin Postgres de pruebas (definí CLOUD_TEST_PG_PASSWORD y levantalo)")
    cfg = _pg_settings()
    name = f"test_savi_cloud_{uuid4().hex[:12]}"
    asyncio.run(_admin_execute(f'CREATE DATABASE "{name}"'))
    try:
        yield (
            f"postgresql+asyncpg://{quote(cfg['user'])}:{quote(cfg['password'])}"
            f"@{cfg['host']}:{cfg['port']}/{name}"
        )
    finally:
        asyncio.run(_admin_execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture
def pg_url() -> Generator[str]:
    with temporary_postgres() as url:
        yield url


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    """SQLite en archivo con el esquema creado desde los modelos (portable, sin servidor)."""
    path = tmp_path / "cloud.db"
    engine = create_sync_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    return f"sqlite+aiosqlite:///{path}"


@pytest.fixture
def clear_settings_cache() -> Callable[[], None]:
    from app.config import get_settings

    return get_settings.cache_clear
