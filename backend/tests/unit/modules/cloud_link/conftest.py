from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.config import Settings
from app.infrastructure.database.base import Base
from app.modules.cloud_link.domain.interfaces import CloudApi
from app.modules.cloud_link.infrastructure.composition import (
    CloudLinkServices,
    build_cloud_link_services,
)
from app.modules.cloud_link.infrastructure.sync_lock import NoopSyncLock

from .support import CLOUD_URL, FakeClock, seed_erp_databases

# Clave de la suite (tests/conftest.py).
_KEY = "sIYQBhcJUxE6vsRRrJvVKa3CtoUj_o8SPDBSAcHDCyM="


@pytest_asyncio.fixture
async def sm(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'cloud_link.db').as_posix()}")

    @event.listens_for(engine.sync_engine, "connect")
    def _pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    await seed_erp_databases(factory)
    yield factory
    await engine.dispose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def make_settings(tmp_path: Path) -> Callable[..., Settings]:
    def build(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "agent_db_engine": "sqlite",
            "agent_db_path": str(tmp_path / "unused.db"),
            "erp_credentials_key": _KEY,
            "savi_cloud_url": CLOUD_URL,
            "savi_cloud_sync_enabled": False,
        }
        values.update(overrides)
        return Settings(**values)  # pyright: ignore[reportArgumentType]

    return build


@pytest.fixture
def make_services(
    sm: async_sessionmaker[AsyncSession],
    clock: FakeClock,
    make_settings: Callable[..., Settings],
) -> Callable[..., CloudLinkServices]:
    def build(api: CloudApi, **overrides: object) -> CloudLinkServices:
        settings = overrides.pop("settings", None) or make_settings()
        return build_cloud_link_services(
            settings=settings,  # pyright: ignore[reportArgumentType]
            sessionmaker=sm,
            cloud_api=api,
            sync_lock=NoopSyncLock(),
            now=clock,
            **overrides,  # pyright: ignore[reportArgumentType]
        )

    return build
