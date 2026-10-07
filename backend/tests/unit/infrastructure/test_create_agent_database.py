"""`ensure_agent_database` contra el Postgres real de desarrollo.

Se salta si no hay un Postgres alcanzable con los datos de `.env`. Crea y
borra sus propias bases y su propio rol; no toca la base de SAVI.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.infrastructure.config import get_settings
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.create_database import (
    AgentDatabaseCreationError,
    _maintenance_url,  # pyright: ignore[reportPrivateUsage]
    ensure_agent_database,
)


def _postgres_settings(**overrides: object) -> Settings:
    base = get_settings()
    return base.model_copy(update={"agent_db_engine": "postgresql", **overrides})


@pytest_asyncio.fixture
async def admin() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        _maintenance_url(_postgres_settings(), "postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as error:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"No hay Postgres alcanzable: {error}")
    yield engine
    await engine.dispose()


async def _exists(admin: AsyncEngine, name: str) -> bool:
    async with admin.connect() as connection:
        found = await connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
        )
    return bool(found)


async def test_creates_the_database_once(admin: AsyncEngine) -> None:
    name = f"test_savi_create_{uuid4().hex[:10]}"
    settings = _postgres_settings(agent_db_name=name)
    try:
        assert await ensure_agent_database(settings) is True
        assert await _exists(admin, name)
        assert await ensure_agent_database(settings) is False
    finally:
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


async def test_a_user_without_createdb_gets_an_actionable_message(admin: AsyncEngine) -> None:
    role = f"test_savi_nocreate_{uuid4().hex[:8]}"
    name = f"test_savi_denied_{uuid4().hex[:10]}"
    async with admin.connect() as connection:
        await connection.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD 'x-test' NOCREATEDB"))
    try:
        settings = _postgres_settings(
            agent_db_name=name, agent_db_user=role, agent_db_password="x-test"
        )
        with pytest.raises(AgentDatabaseCreationError, match="CREATE DATABASE"):
            await ensure_agent_database(settings)
        assert not await _exists(admin, name)
    finally:
        async with admin.connect() as connection:
            await connection.execute(text(f"DROP ROLE IF EXISTS {role}"))


async def test_sqlite_is_left_alone() -> None:
    settings = get_settings().model_copy(update={"agent_db_engine": "sqlite"})

    assert await ensure_agent_database(settings) is False
