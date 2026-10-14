"""Pruebas contra un Postgres real (base desechable creada y borrada por el test).

Se saltan si no hay `CLOUD_TEST_PG_PASSWORD` o el servidor no responde. Ver README.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

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
TABLES = {
    "clients",
    "instances",
    "enrollment_tokens",
    "heartbeats",
    "ingest_batches",
    "ev_turns",
    "ev_conversations",
    "ev_sessions",
    "ev_free_queries",
    "instance_databases",
    "staff_users",
    "staff_sessions",
    "audit_log",
    "alerts",
    "alert_rules",
}


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


def test_http_concurrent_redeem_and_concurrent_batches(pg_url: str) -> None:
    """Sobre Postgres real: un canje gana; el mismo lote en paralelo se procesa una sola vez."""
    command.upgrade(_alembic(pg_url), "head")
    body = {
        "instance": {
            "name": "SRV",
            "deployment_mode": "server",
            "os": "Linux",
            "agent_db_engine": "postgresql",
            "fingerprint": "fp",
        }
    }
    events = [
        {
            "schema": "turn/1",
            "source_id": f"t{i}",
            "occurred_at": "2026-01-01T11:00:00Z",
            "data": {
                "conversation_ref": "5d0f4f0e-6f5b-4d0b-8f0e-6a4f3c2b1a09",
                "user_ref": "0123456789abcdef0123456789abcdef",
                "input_tokens": 1,
                "output_tokens": 1,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        }
        for i in range(2)
    ]

    async def run() -> None:
        app = create_app(Settings(database_url=pg_url, env="test"))
        maker = app.state.sessionmaker
        try:
            async with maker() as s, s.begin():
                clients = SqlAlchemyClientRepository(s)
                await CreateClientUseCase(clients, utc_now).execute(code="FARMX", name="F")
                created = await CreateEnrollmentTokenUseCase(
                    clients, SqlAlchemyEnrollmentTokenRepository(s), utc_now
                ).execute(client_code="FARMX")

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://t"
            ) as http:
                redeems = await asyncio.gather(
                    *(
                        http.post(
                            "/api/v1/enrollments/redeem", json={"token": created.plaintext, **body}
                        )
                        for _ in range(5)
                    )
                )
                assert sorted(r.status_code for r in redeems) == [201, 404, 404, 404, 404]
                winner = next(r for r in redeems if r.status_code == 201).json()
                auth = {"Authorization": f"Bearer {winner['instance_secret']}"}

                same_batch = {
                    "batch_id": "0b8e6c3a-5f1d-4e21-8a4b-2f7c9d1e3a55",
                    "sent_at": "2026-01-01T12:00:00Z",
                    "events": events,
                }
                answers = await asyncio.gather(
                    *(
                        http.post("/api/v1/instances/ingest", json=same_batch, headers=auth)
                        for _ in range(5)
                    )
                )
                assert {r.status_code for r in answers} == {200}
                assert {json.dumps(r.json(), sort_keys=True) for r in answers} == {
                    json.dumps({"accepted": 2, "duplicates": 0, "rejected": []}, sort_keys=True)
                }

                other_batches = await asyncio.gather(
                    *(
                        http.post(
                            "/api/v1/instances/ingest",
                            json={**same_batch, "batch_id": str(uuid4())},
                            headers=auth,
                        )
                        for _ in range(5)
                    )
                )
                assert sum(r.json()["accepted"] for r in other_batches) == 0
                assert sum(r.json()["duplicates"] for r in other_batches) == 10

            async with app.state.engine.connect() as conn:
                instances = (
                    await conn.execute(text("SELECT count(*) FROM instances"))
                ).scalar_one()
                turns = (await conn.execute(text("SELECT count(*) FROM ev_turns"))).scalar_one()
                batches = (
                    await conn.execute(text("SELECT count(*) FROM ingest_batches"))
                ).scalar_one()
            assert (instances, turns, batches) == (1, 2, 6)
        finally:
            await app.state.engine.dispose()

    asyncio.run(run())


def test_audit_log_is_append_only(pg_url: str) -> None:
    """El trigger de 0003 rechaza UPDATE, DELETE y TRUNCATE aunque se use el dueño."""
    command.upgrade(_alembic(pg_url), "head")

    async def run() -> list[str]:
        engine = create_engine(pg_url)
        errors: list[str] = []
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO audit_log (id, occurred_at, action) "
                        "VALUES (:id, now(), 'test.insert')"
                    ),
                    {"id": uuid4()},
                )
            for statement in (
                "UPDATE audit_log SET action = 'x'",
                "DELETE FROM audit_log",
                "TRUNCATE audit_log",
            ):
                try:
                    async with engine.begin() as conn:
                        await conn.execute(text(statement))
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc))
            async with engine.connect() as conn:
                count = (await conn.execute(text("SELECT count(*) FROM audit_log"))).scalar_one()
            assert count == 1
        finally:
            await engine.dispose()
        return errors

    errors = asyncio.run(run())
    assert len(errors) == 3
    assert all("solo inserción" in e for e in errors)
