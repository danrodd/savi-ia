"""Pruebas contra un Postgres real (base desechable creada y borrada por el test).

Se saltan si no hay `CLOUD_TEST_PG_PASSWORD` o el servidor no responde. Ver README.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from alembic import command
from app.config import Settings
from app.db import create_engine, create_sessionmaker
from app.main import create_app
from app.models import Base
from app.modules.clients.application import CreateClientUseCase
from app.modules.clients.infrastructure import SqlAlchemyClientRepository
from app.modules.enrollments.application import (
    CreateEnrollmentTokenUseCase,
    RedeemEnrollmentTokenUseCase,
)
from app.modules.enrollments.domain import EnrollmentTokenInvalid, InstanceInfo
from app.modules.enrollments.infrastructure import SqlAlchemyEnrollmentTokenRepository
from app.modules.instances.infrastructure import SqlAlchemyInstanceRepository
from app.shared.clock import utc_now

ROOT = Path(__file__).resolve().parents[1]
TABLES = {"clients", "instances", "enrollment_tokens"}


def _alembic(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


def _tables(url: str) -> set[str]:
    async def run() -> set[str]:
        engine = create_engine(url)
        try:
            async with engine.connect() as conn:
                names = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
        finally:
            await engine.dispose()
        return names

    return asyncio.run(run()) - {"alembic_version"}


def test_migration_upgrade_and_downgrade(pg_url: str) -> None:
    cfg = _alembic(pg_url)
    command.upgrade(cfg, "head")
    assert _tables(pg_url) == TABLES
    command.downgrade(cfg, "base")
    assert _tables(pg_url) == set()
    command.upgrade(cfg, "head")  # reaplicable
    assert _tables(pg_url) == TABLES


def test_migrated_schema_matches_models(pg_url: str) -> None:
    command.upgrade(_alembic(pg_url), "head")

    async def diff() -> list[object]:
        engine = create_engine(pg_url)
        try:
            async with engine.connect() as conn:

                def compare(sync_conn: object) -> list[object]:
                    ctx = MigrationContext.configure(
                        sync_conn,  # type: ignore[arg-type]
                        opts={"compare_type": True},
                    )
                    return list(compare_metadata(ctx, Base.metadata))

                return await conn.run_sync(compare)
        finally:
            await engine.dispose()

    assert asyncio.run(diff()) == []


def test_ready_and_health_against_postgres(pg_url: str) -> None:
    command.upgrade(_alembic(pg_url), "head")

    async def run() -> tuple[int, int]:
        app = create_app(Settings(database_url=pg_url, env="test"))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as http:
            health = await http.get("/health")
            ready = await http.get("/ready")
        await app.state.engine.dispose()
        return health.status_code, ready.status_code

    assert asyncio.run(run()) == (200, 200)


def test_concurrent_redeem_creates_single_instance(pg_url: str) -> None:
    command.upgrade(_alembic(pg_url), "head")
    info = InstanceInfo(
        name="SRV",
        deployment_mode="server",
        version=None,
        commit=None,
        os="Linux",
        agent_db_engine="postgresql",
        fingerprint="fp",
    )

    async def run() -> tuple[int, int]:
        engine = create_engine(pg_url)
        maker = create_sessionmaker(engine)
        try:
            async with maker() as s, s.begin():
                clients = SqlAlchemyClientRepository(s)
                await CreateClientUseCase(clients, utc_now).execute(code="FARMX", name="F")
                created = await CreateEnrollmentTokenUseCase(
                    clients, SqlAlchemyEnrollmentTokenRepository(s), utc_now
                ).execute(client_code="FARMX")

            async def attempt() -> bool:
                async with maker() as s, s.begin():
                    try:
                        await RedeemEnrollmentTokenUseCase(
                            SqlAlchemyClientRepository(s),
                            SqlAlchemyEnrollmentTokenRepository(s),
                            SqlAlchemyInstanceRepository(s),
                            utc_now,
                        ).execute(token=created.plaintext, info=info)
                    except EnrollmentTokenInvalid:
                        return False
                    return True

            results = await asyncio.gather(*(attempt() for _ in range(5)))
            async with engine.connect() as conn:
                count = (await conn.execute(text("SELECT count(*) FROM instances"))).scalar_one()
            return sum(results), int(count)
        finally:
            await engine.dispose()

    wins, instances = asyncio.run(run())
    assert (wins, instances) == (1, 1)
