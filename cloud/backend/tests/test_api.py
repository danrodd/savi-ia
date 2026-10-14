"""API de Cloud (§3, §8.3) sobre SQLite: vinculación, autenticación, heartbeat e ingest.

Las pruebas que dependen de Postgres real (concurrencia, migraciones) están en
`test_postgres.py`.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.main import create_app
from app.modules.clients.application import CreateClientUseCase
from app.modules.clients.infrastructure import SqlAlchemyClientRepository
from app.modules.enrollments.application import CreateEnrollmentTokenUseCase
from app.modules.enrollments.infrastructure import SqlAlchemyEnrollmentTokenRepository
from app.modules.instances.application import (
    ActivateInstanceUseCase,
    RevokeInstanceUseCase,
    SuspendInstanceUseCase,
)
from app.modules.instances.infrastructure import InstanceModel, SqlAlchemyInstanceRepository
from tests.contract_files import validate_document
from tests.fakes import FakeClock

HEARTBEAT = "/api/v1/instances/heartbeat"
INGEST = "/api/v1/instances/ingest"
ROTATE = "/api/v1/instances/credentials/rotate"
REDEEM = "/api/v1/enrollments/redeem"

USER_REF = "0123456789abcdef0123456789abcdef"
CONVERSATION = "5d0f4f0e-6f5b-4d0b-8f0e-6a4f3c2b1a09"
DATABASE = "7a1f3c52-9d4e-4b6a-8c0d-1e2f3a4b5c6d"


@dataclass
class Enrolled:
    instance_id: str
    secret: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.secret}"}


@dataclass
class Env:
    http: httpx.AsyncClient
    app: FastAPI
    clock: FakeClock

    @property
    def maker(self) -> async_sessionmaker[AsyncSession]:
        maker: async_sessionmaker[AsyncSession] = self.app.state.sessionmaker
        return maker

    async def new_token(self, client_code: str = "FARMX") -> str:
        async with self.maker() as s, s.begin():
            clients = SqlAlchemyClientRepository(s)
            if await clients.get_by_code(client_code) is None:
                await CreateClientUseCase(clients, self.clock).execute(
                    code=client_code, name="Farmacias X"
                )
            created = await CreateEnrollmentTokenUseCase(
                clients, SqlAlchemyEnrollmentTokenRepository(s), self.clock
            ).execute(client_code=client_code)
        return created.plaintext

    def enroll_body(self, token: str, fingerprint: str = "fp-1") -> dict[str, Any]:
        return {
            "token": token,
            "instance": {
                "name": "SRV-FARMX",
                "deployment_mode": "server",
                "version": "v1.2.0",
                "commit": "2ce0b85",
                "os": "Windows Server 2022",
                "agent_db_engine": "postgresql",
                "fingerprint": fingerprint,
            },
        }

    async def enroll(self, client_code: str = "FARMX", fingerprint: str = "fp-1") -> Enrolled:
        token = await self.new_token(client_code)
        res = await self.http.post(REDEEM, json=self.enroll_body(token, fingerprint))
        assert res.status_code == 201, res.text
        body = res.json()
        return Enrolled(body["instance_id"], body["instance_secret"])

    def heartbeat_body(self, fingerprint: str = "fp-1", **extra: Any) -> dict[str, Any]:
        return {
            "sent_at": self.clock.now.isoformat(),
            "fingerprint": fingerprint,
            "version": "v1.2.0",
            "deployment_mode": "server",
            **extra,
        }

    async def count(self, table: str) -> int:
        async with self.maker() as s:
            return int((await s.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one())

    async def instance(self, instance_id: str) -> InstanceModel:
        async with self.maker() as s:
            model = await s.get(InstanceModel, UUID(instance_id))
            assert model is not None
            return model

    async def send_batch(
        self, who: Enrolled, events: list[dict[str, Any]], batch_id: str | None = None
    ) -> httpx.Response:
        body = {
            "batch_id": batch_id or str(uuid4()),
            "sent_at": self.clock.now.isoformat(),
            "events": events,
        }
        return await self.http.post(INGEST, json=body, headers=who.auth)


@pytest.fixture
async def env(sqlite_url: str) -> AsyncGenerator[Env]:
    clock = FakeClock()
    app = create_app(Settings(database_url=sqlite_url, env="test"), clock=clock)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield Env(http, app, clock)
    await app.state.engine.dispose()


def turn(source_id: str, **data: Any) -> dict[str, Any]:
    return {
        "schema": "turn/1",
        "source_id": source_id,
        "occurred_at": "2026-01-01T11:00:00Z",
        "data": {
            "conversation_ref": CONVERSATION,
            "user_ref": USER_REF,
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cost_usd": "0.001500",
            **data,
        },
    }


def assert_matches_schema(stem: str, document: Any) -> None:
    validate_document(stem, document)


def assert_error(res: httpx.Response, status: int, code: str) -> None:
    assert res.status_code == status, res.text
    body = res.json()
    assert set(body) == {"errorCode", "message"}
    assert body["errorCode"] == code


# --- vinculación --------------------------------------------------------------------------


async def test_redeem_creates_instance_and_matches_contract(env: Env) -> None:
    token = await env.new_token()
    res = await env.http.post(REDEEM, json=env.enroll_body(token))
    assert res.status_code == 201
    body = res.json()
    assert_matches_schema("enroll.response", body)
    assert body["client"]["code"] == "FARMX"
    assert body["policy"] == {
        "heartbeat_seconds": 300,
        "ingest_seconds": 300,
        "max_batch_events": 500,
        "sync_enabled": True,
        "config_locked": False,
        "allow_local_cli": False,
        "identity_mode": "pseudonym",
    }
    stored = await env.instance(body["instance_id"])
    assert stored.status == "active"
    assert stored.secret_hash != body["instance_secret"].encode()  # solo se guarda el hash


async def test_redeem_token_is_single_use(env: Env) -> None:
    token = await env.new_token()
    first = await env.http.post(REDEEM, json=env.enroll_body(token))
    second = await env.http.post(REDEEM, json=env.enroll_body(token))
    assert first.status_code == 201
    assert_error(second, 404, "enrollment_token_invalid")
    assert await env.count("instances") == 1


async def test_redeem_unknown_expired_and_used_tokens_look_identical(env: Env) -> None:
    unknown = await env.http.post(REDEEM, json=env.enroll_body("svk_enr_nope"))
    expired_token = await env.new_token()
    env.clock.advance(hours=73)
    expired = await env.http.post(REDEEM, json=env.enroll_body(expired_token))
    used_token = await env.new_token()
    await env.http.post(REDEEM, json=env.enroll_body(used_token))
    used = await env.http.post(REDEEM, json=env.enroll_body(used_token))
    for res in (unknown, expired, used):
        assert_error(res, 404, "enrollment_token_invalid")
    assert unknown.json() == expired.json() == used.json()


async def test_redeem_suspended_client_is_forbidden(env: Env) -> None:
    token = await env.new_token()
    async with env.maker() as s, s.begin():
        await s.execute(text("UPDATE clients SET status = 'suspended'"))
    res = await env.http.post(REDEEM, json=env.enroll_body(token))
    assert_error(res, 403, "client_suspended")
    assert await env.count("instances") == 0


async def test_redeem_is_rate_limited_per_ip(env: Env) -> None:
    for _ in range(10):
        res = await env.http.post(REDEEM, json=env.enroll_body("svk_enr_bad"))
        assert res.status_code == 404
    blocked = await env.http.post(REDEEM, json=env.enroll_body("svk_enr_bad"))
    assert_error(blocked, 429, "too_many_requests")
    assert int(blocked.headers["retry-after"]) > 0
    env.clock.advance(minutes=16)
    again = await env.http.post(REDEEM, json=env.enroll_body("svk_enr_bad"))
    assert again.status_code == 404


async def test_redeem_with_invalid_body_uses_error_format(env: Env) -> None:
    res = await env.http.post(REDEEM, json={"token": "x"})
    assert_error(res, 422, "validation_error")


# --- autenticación ------------------------------------------------------------------------


async def test_missing_or_wrong_bearer_is_unauthorized(env: Env) -> None:
    await env.enroll()
    missing = await env.http.post(HEARTBEAT, json=env.heartbeat_body())
    wrong = await env.http.post(
        HEARTBEAT, json=env.heartbeat_body(), headers={"Authorization": "Bearer svk_ins_nope"}
    )
    other_scheme = await env.http.post(
        HEARTBEAT, json=env.heartbeat_body(), headers={"Authorization": "Basic abc"}
    )
    for res in (missing, wrong, other_scheme):
        assert_error(res, 401, "instance_unauthorized")


async def test_rotation_keeps_previous_secret_for_24_hours(env: Env) -> None:
    old = await env.enroll()
    rotated = await env.http.post(ROTATE, headers=old.auth)
    assert rotated.status_code == 200
    new = Enrolled(old.instance_id, rotated.json()["instance_secret"])
    assert new.secret != old.secret

    body = env.heartbeat_body()
    assert (await env.http.post(HEARTBEAT, json=body, headers=new.auth)).status_code == 200
    assert (await env.http.post(HEARTBEAT, json=body, headers=old.auth)).status_code == 200

    env.clock.advance(hours=23, minutes=59)
    assert (
        await env.http.post(HEARTBEAT, json=env.heartbeat_body(), headers=old.auth)
    ).status_code == 200

    env.clock.advance(minutes=2)  # ya pasaron 24 h
    expired = await env.http.post(HEARTBEAT, json=env.heartbeat_body(), headers=old.auth)
    assert_error(expired, 401, "instance_unauthorized")
    assert (
        await env.http.post(HEARTBEAT, json=env.heartbeat_body(), headers=new.auth)
    ).status_code == 200


async def test_revoked_instance_gets_instance_revoked(env: Env) -> None:
    who = await env.enroll()
    async with env.maker() as s, s.begin():
        await RevokeInstanceUseCase(SqlAlchemyInstanceRepository(s), env.clock).execute(
            UUID(who.instance_id)
        )
    for res in (
        await env.http.post(HEARTBEAT, json=env.heartbeat_body(), headers=who.auth),
        await env.send_batch(who, []),
        await env.http.post(ROTATE, headers=who.auth),
    ):
        assert_error(res, 401, "instance_revoked")


# --- heartbeat ----------------------------------------------------------------------------


async def test_heartbeat_records_state_and_clock_skew(env: Env) -> None:
    who = await env.enroll()
    sent = env.clock.now - timedelta(seconds=90)
    body = env.heartbeat_body(
        sent_at=sent.isoformat(),
        version="v1.3.0",
        commit="abc1234",
        tls=True,
        active_sessions=4,
        warnings=["http_without_tls"],
    )
    res = await env.http.post(HEARTBEAT, json=body, headers=who.auth)
    assert res.status_code == 200
    answer = res.json()
    assert_matches_schema("heartbeat.response", answer)
    assert answer["instance_status"] == "active"
    assert answer["notices"] == []
    assert answer["policy"]["sync_enabled"] is True

    stored = await env.instance(who.instance_id)
    assert stored.clock_skew_seconds == 90
    assert stored.version == "v1.3.0"
    assert stored.commit == "abc1234"
    assert stored.last_seen_at is not None
    assert stored.last_heartbeat is not None
    assert stored.last_heartbeat["active_sessions"] == 4
    assert await env.count("heartbeats") == 1


async def test_fingerprint_mismatch_suspends_and_blocks_ingest(env: Env) -> None:
    who = await env.enroll(fingerprint="fp-original")
    res = await env.http.post(
        HEARTBEAT, json=env.heartbeat_body(fingerprint="fp-clon"), headers=who.auth
    )
    assert res.status_code == 200
    answer = res.json()
    assert answer["instance_status"] == "suspended"
    assert answer["policy"]["sync_enabled"] is False
    assert [n["code"] for n in answer["notices"]] == ["fingerprint_mismatch"]
    stored = await env.instance(who.instance_id)
    assert (stored.status, stored.status_reason) == ("suspended", "fingerprint_mismatch")

    sent = await env.send_batch(who, [turn("t1")])
    assert sent.json() == {"accepted": 0, "duplicates": 0, "rejected": []}
    assert await env.count("ev_turns") == 0


async def test_activating_after_fingerprint_mismatch_accepts_the_new_fingerprint(env: Env) -> None:
    who = await env.enroll(fingerprint="fp-original")
    await env.http.post(HEARTBEAT, json=env.heartbeat_body("fp-nuevo"), headers=who.auth)
    async with env.maker() as s, s.begin():
        await ActivateInstanceUseCase(SqlAlchemyInstanceRepository(s), env.clock).execute(
            UUID(who.instance_id)
        )
    res = await env.http.post(HEARTBEAT, json=env.heartbeat_body("fp-nuevo"), headers=who.auth)
    assert res.json()["instance_status"] == "active"
    assert res.json()["notices"] == []
    assert (await env.send_batch(who, [turn("t1")])).json()["accepted"] == 1


async def test_heartbeat_is_rate_limited_per_instance(env: Env) -> None:
    who = await env.enroll()
    other = await env.enroll(fingerprint="fp-2")
    for _ in range(60):
        res = await env.http.post(HEARTBEAT, json=env.heartbeat_body(), headers=who.auth)
        assert res.status_code == 200
    blocked = await env.http.post(HEARTBEAT, json=env.heartbeat_body(), headers=who.auth)
    assert_error(blocked, 429, "too_many_requests")
    assert int(blocked.headers["retry-after"]) > 0
    # El límite es por instancia: otra instancia no se ve afectada.
    ok = await env.http.post(HEARTBEAT, json=env.heartbeat_body("fp-2"), headers=other.auth)
    assert ok.status_code == 200
    env.clock.advance(seconds=61)
    again = await env.http.post(HEARTBEAT, json=env.heartbeat_body(), headers=who.auth)
    assert again.status_code == 200


# --- ingest -------------------------------------------------------------------------------


async def test_ingest_accepts_all_streams(env: Env) -> None:
    who = await env.enroll()
    events = [
        turn("t1", tools=[{"name": "consultar_datos", "status": "ok"}], action="send"),
        {
            "schema": "conversation/1",
            "source_id": CONVERSATION,
            "occurred_at": "2026-01-01T10:00:00Z",
            "data": {"conversation_ref": CONVERSATION, "user_ref": USER_REF},
        },
        {
            "schema": "session/1",
            "source_id": "jti-1",
            "occurred_at": "2026-01-01T09:00:00Z",
            "data": {"user_ref": USER_REF, "database_ref": DATABASE},
        },
        {
            "schema": "free_query/1",
            "source_id": "fq-1",
            "occurred_at": "2026-01-01T11:30:00Z",
            "data": {"conversation_ref": CONVERSATION, "result": "ok", "returned_rows": 3},
        },
        {
            "schema": "database/1",
            "source_id": f"{DATABASE}:2026-01-01",
            "occurred_at": "2026-01-01T06:00:00Z",
            "data": {
                "database_ref": DATABASE,
                "code": "NORTE",
                "name": "Sede Norte",
                "is_active": True,
                "is_usable": True,
                "credentials_unreadable": False,
            },
        },
    ]
    res = await env.send_batch(who, events)
    assert res.status_code == 200, res.text
    assert_matches_schema("ingest.response", res.json())
    assert res.json() == {"accepted": 5, "duplicates": 0, "rejected": []}
    for table in (
        "ev_turns",
        "ev_conversations",
        "ev_sessions",
        "ev_free_queries",
        "instance_databases",
    ):
        assert await env.count(table) == 1, table


async def test_repeated_batch_returns_original_response_without_reprocessing(env: Env) -> None:
    who = await env.enroll()
    batch_id = str(uuid4())
    first = await env.send_batch(who, [turn("t1"), turn("t2")], batch_id)
    again = await env.send_batch(who, [turn("t1"), turn("t2"), turn("t3")], batch_id)
    assert first.json() == {"accepted": 2, "duplicates": 0, "rejected": []}
    assert again.json() == first.json()  # la respuesta original, aunque el contenido difiera
    assert await env.count("ev_turns") == 2
    assert await env.count("ingest_batches") == 1


async def test_repeated_event_in_another_batch_counts_as_duplicate(env: Env) -> None:
    who = await env.enroll()
    await env.send_batch(who, [turn("t1"), turn("t2")])
    res = await env.send_batch(who, [turn("t2"), turn("t3")])
    assert res.json() == {"accepted": 1, "duplicates": 1, "rejected": []}
    assert await env.count("ev_turns") == 3
    # Repetido dentro del mismo lote.
    res = await env.send_batch(who, [turn("t4"), turn("t4")])
    assert res.json() == {"accepted": 1, "duplicates": 1, "rejected": []}


async def test_event_idempotency_is_scoped_to_the_instance(env: Env) -> None:
    first = await env.enroll()
    second = await env.enroll(fingerprint="fp-2")
    assert (await env.send_batch(first, [turn("t1")])).json()["accepted"] == 1
    assert (await env.send_batch(second, [turn("t1")])).json()["accepted"] == 1
    assert await env.count("ev_turns") == 2


async def test_invalid_events_are_rejected_without_failing_the_batch(env: Env) -> None:
    who = await env.enroll()
    bad_extra = turn("bad-extra", sql="SELECT 1")  # campo fuera de la lista blanca
    bad_type = turn("bad-type", input_tokens="mucho")
    unknown: dict[str, Any] = {
        "schema": "invoice/1",
        "source_id": "inv-1",
        "occurred_at": "2026-01-01T00:00:00Z",
        "data": {},
    }
    future = {**turn("t-v2"), "schema": "turn/2"}
    no_source: dict[str, Any] = {
        "schema": "turn/1",
        "occurred_at": "2026-01-01T00:00:00Z",
        "data": {},
    }
    res = await env.send_batch(
        who, [turn("ok-1"), bad_extra, unknown, bad_type, future, no_source, turn("ok-2")]
    )
    assert res.status_code == 200
    body = res.json()
    assert_matches_schema("ingest.response", body)
    assert body["accepted"] == 2
    assert body["duplicates"] == 0
    assert {(r["source_id"], r["reason"]) for r in body["rejected"]} == {
        ("bad-extra", "invalid_event"),
        ("bad-type", "invalid_event"),
        ("inv-1", "unknown_schema"),
        ("t-v2", "unknown_schema"),
        ("", "invalid_event"),  # sin source_id: no se puede identificar, pero se informa
    }
    assert await env.count("ev_turns") == 2


async def test_suspended_instance_gets_zero_accepted_and_nothing_is_stored(env: Env) -> None:
    who = await env.enroll()
    async with env.maker() as s, s.begin():
        await SuspendInstanceUseCase(SqlAlchemyInstanceRepository(s), env.clock).execute(
            UUID(who.instance_id)
        )
    batch_id = str(uuid4())
    res = await env.send_batch(who, [turn("t1")], batch_id)
    assert res.status_code == 200
    assert res.json() == {"accepted": 0, "duplicates": 0, "rejected": []}
    assert await env.count("ev_turns") == 0
    assert await env.count("ingest_batches") == 0

    # Al reactivarla, el mismo lote se procesa completo: no se perdió nada.
    async with env.maker() as s, s.begin():
        await ActivateInstanceUseCase(SqlAlchemyInstanceRepository(s), env.clock).execute(
            UUID(who.instance_id)
        )
    again = await env.send_batch(who, [turn("t1")], batch_id)
    assert again.json() == {"accepted": 1, "duplicates": 0, "rejected": []}


async def test_gzip_body_is_accepted(env: Env) -> None:
    who = await env.enroll()
    body = {"batch_id": str(uuid4()), "sent_at": env.clock.now.isoformat(), "events": [turn("t1")]}
    res = await env.http.post(
        INGEST,
        content=gzip.compress(json.dumps(body).encode()),
        headers={**who.auth, "Content-Encoding": "gzip", "Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json()["accepted"] == 1


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"sent_at": "2026-01-01T00:00:00Z", "events": []}, "invalid_envelope"),
        (
            {"batch_id": "no-es-uuid", "sent_at": "2026-01-01T00:00:00Z", "events": []},
            "invalid_envelope",
        ),
        (
            {"batch_id": str(uuid4()), "sent_at": "2026-01-01T00:00:00", "events": []},
            "invalid_envelope",
        ),
        (
            {"batch_id": str(uuid4()), "sent_at": "2026-01-01T00:00:00Z", "events": "x"},
            "invalid_envelope",
        ),
        (
            {"batch_id": str(uuid4()), "sent_at": "2026-01-01T00:00:00Z", "events": ["x"]},
            "invalid_envelope",
        ),
        ([1, 2, 3], "invalid_envelope"),
    ],
)
async def test_invalid_envelope_is_422(env: Env, payload: Any, code: str) -> None:
    who = await env.enroll()
    res = await env.http.post(INGEST, json=payload, headers=who.auth)
    assert_error(res, 422, code)
    assert await env.count("ingest_batches") == 0


async def test_non_json_and_bad_gzip_are_422(env: Env) -> None:
    who = await env.enroll()
    garbage = await env.http.post(INGEST, content=b"{no es json", headers=who.auth)
    assert_error(garbage, 422, "invalid_envelope")
    bad_gzip = await env.http.post(
        INGEST, content=b"no es gzip", headers={**who.auth, "Content-Encoding": "gzip"}
    )
    assert_error(bad_gzip, 422, "invalid_envelope")


async def test_more_than_500_events_is_413(env: Env) -> None:
    who = await env.enroll()
    ok = await env.send_batch(who, [turn(f"t{i}") for i in range(500)])
    assert ok.json()["accepted"] == 500
    res = await env.send_batch(who, [{"schema": "turn/1"}] * 501)
    assert_error(res, 413, "batch_too_large")


async def test_body_over_5mb_is_413_plain_and_gzipped(env: Env) -> None:
    who = await env.enroll()
    pad = "a" * (5 * 1024 * 1024 + 1)
    envelope: dict[str, Any] = {
        "batch_id": str(uuid4()),
        "sent_at": env.clock.now.isoformat(),
        "events": [],
        "pad": pad,
    }
    plain = await env.http.post(INGEST, content=json.dumps(envelope).encode(), headers=who.auth)
    assert_error(plain, 413, "batch_too_large")
    # Pesa unos KB comprimido pero 5 MB+ descomprimido: la bomba se corta igual.
    bomb = await env.http.post(
        INGEST,
        content=gzip.compress(json.dumps(envelope).encode()),
        headers={**who.auth, "Content-Encoding": "gzip"},
    )
    assert_error(bomb, 413, "batch_too_large")


async def test_unauthorized_ingest_never_reads_the_body(env: Env) -> None:
    res = await env.http.post(INGEST, content=b"{no es json")
    assert_error(res, 401, "instance_unauthorized")


async def test_ingest_is_rate_limited_per_instance(env: Env) -> None:
    who = await env.enroll()
    for _ in range(30):
        assert (await env.send_batch(who, [])).status_code == 200
    blocked = await env.send_batch(who, [])
    assert_error(blocked, 429, "too_many_requests")
    assert int(blocked.headers["retry-after"]) > 0


async def test_unknown_route_uses_error_format(env: Env) -> None:
    res = await env.http.get("/api/v1/nope")
    assert_error(res, 404, "not_found")
