"""Métricas (§4.1): cada definición contra un dataset chico con valores escritos a mano."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.ingest.infrastructure import (
    EvConversationModel,
    EvFreeQueryModel,
    EvSessionModel,
    EvTurnModel,
    InstanceDatabaseModel,
)
from app.modules.metrics.definitions import METRICS
from app.modules.metrics.queries import percentile
from app.modules.staff.domain import Role
from tests.console_helpers import ConsoleEnv, Session
from tests.test_console_api import API, Fixture, Linked, link_instance, make_client

DB_A = UUID("00000000-0000-4000-8000-00000000000a")
DB_B = UUID("00000000-0000-4000-8000-00000000000b")
INSTANCE = UUID("00000000-0000-4000-8000-0000000000ff")


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


@dataclass
class Dataset:
    client_id: str
    other_client_id: str


def _turn(
    client: UUID,
    source: str,
    at: str,
    user: str,
    provider: str,
    model: str,
    finish: str,
    tokens: tuple[int, int, int, int],
    cost: str | None,
    latency: int | None,
    database: UUID,
    tools: list[dict[str, str]],
) -> EvTurnModel:
    return EvTurnModel(
        instance_id=INSTANCE,
        source_id=source,
        client_id=client,
        occurred_at=utc(at),
        conversation_ref=uuid4(),
        database_ref=database,
        user_ref=user,
        provider=provider,
        model=model,
        finish_reason=finish,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        cache_read_input_tokens=tokens[2],
        cache_creation_input_tokens=tokens[3],
        cost_usd=Decimal(cost) if cost is not None else None,
        tools=tools,
        latency_ms=latency,
        action="send",
    )


async def seed(fx: Fixture) -> Dataset:
    client_id = await make_client(fx, "FARMX", "Farmacias X")
    other_id = await make_client(fx, "OTRO1", "Otro cliente")
    c, o = UUID(client_id), UUID(other_id)
    ok = {"name": "consultar_datos", "status": "ok"}
    rows: list[Any] = [
        _turn(
            c,
            "t1",
            "2025-12-30T10:00:00Z",
            "u1",
            "claude",
            "sonnet",
            "complete",
            (100, 50, 0, 0),
            "0.010000",
            1000,
            DB_A,
            [ok],
        ),
        _turn(
            c,
            "t2",
            "2025-12-30T11:00:00Z",
            "u1",
            "claude",
            "sonnet",
            "error",
            (10, 0, 0, 0),
            "0.001000",
            3000,
            DB_A,
            [{"name": "consultar_datos", "status": "error"}],
        ),
        # 23:59:59 en Bogotá del 30/12 (04:59:59Z del 31/12): todavía es el día 30.
        _turn(
            c,
            "t3",
            "2025-12-31T04:59:59Z",
            "u2",
            "openai",
            "luna",
            "complete",
            (200, 100, 50, 50),
            None,
            2000,
            DB_B,
            [{"name": "consultar_conocimiento", "status": "ok", "tipo": "modulo"}],
        ),
        # 00:00:00 en Bogotá del 31/12 (05:00:00Z): ya es el día 31.
        _turn(
            c,
            "t4",
            "2025-12-31T05:00:00Z",
            "u2",
            "openai",
            "luna",
            "interrupted",
            (20, 5, 0, 0),
            "0.000500",
            None,
            DB_B,
            [],
        ),
        _turn(
            c,
            "t5",
            "2026-01-01T09:00:00Z",
            "u3",
            "claude",
            "sonnet",
            "truncated",
            (300, 300, 0, 0),
            "0.020000",
            5000,
            DB_A,
            [ok, {"name": "consultar_conocimiento", "status": "ok", "tipo": "modulo"}],
        ),
        # De otro cliente: no debe aparecer en ningún total.
        _turn(
            o,
            "x1",
            "2025-12-31T10:00:00Z",
            "z9",
            "claude",
            "sonnet",
            "complete",
            (999, 999, 0, 0),
            "9.000000",
            9999,
            DB_A,
            [ok],
        ),
        # Fuera del período por defecto (más de 30 días atrás).
        _turn(
            c,
            "old",
            "2025-11-01T10:00:00Z",
            "u1",
            "claude",
            "sonnet",
            "complete",
            (1, 1, 0, 0),
            "5.000000",
            1,
            DB_A,
            [],
        ),
    ]
    for source, at, client in (
        ("c1", "2025-12-30T10:00:00Z", c),
        ("c2", "2025-12-31T10:00:00Z", c),
        ("c-old", "2025-11-01T10:00:00Z", c),
    ):
        rows.append(
            EvConversationModel(
                instance_id=INSTANCE,
                source_id=source,
                client_id=client,
                occurred_at=utc(at),
                conversation_ref=uuid4(),
                database_ref=DB_A,
                user_ref="u1",
            )
        )
    for source, user in (("s1", "u1"), ("s2", "u2"), ("s3", "u3"), ("s4", "u4"), ("s5", "u1")):
        rows.append(
            EvSessionModel(
                instance_id=INSTANCE,
                source_id=source,
                client_id=c,
                occurred_at=utc("2025-12-31T12:00:00Z"),
                user_ref=user,
                database_ref=DB_A,
            )
        )
    for source, result in (("q1", "ok"), ("q2", "ok"), ("q3", "ok"), ("q4", "sql_rejected")):
        rows.append(
            EvFreeQueryModel(
                instance_id=INSTANCE,
                source_id=source,
                client_id=c,
                occurred_at=utc("2025-12-31T12:00:00Z"),
                result=result,
            )
        )
    for ref, name, snapshot in (
        (DB_A, "Sede Norte", date(2025, 12, 30)),
        (DB_A, "Sede Norte (nuevo nombre)", date(2025, 12, 31)),
        (DB_B, "Sede Sur", date(2025, 12, 31)),
    ):
        rows.append(
            InstanceDatabaseModel(
                instance_id=INSTANCE,
                database_ref=ref,
                snapshot_date=snapshot,
                client_id=c,
                occurred_at=utc(f"{snapshot.isoformat()}T12:00:00Z"),
                code=name[:6].upper(),
                name=name,
                is_active=True,
                is_usable=True,
                credentials_unreadable=False,
                last_connection_ok_at=None,
            )
        )
    async with fx.console.maker() as s, s.begin():
        s.add_all(rows)
    return Dataset(client_id, other_id)


@pytest.fixture
async def fx(console: ConsoleEnv) -> Fixture:
    admin = await console.onboard("admin@seo.example", Role.ADMIN)
    soporte = await console.onboard("soporte@seo.example", Role.SOPORTE)
    comercial = await console.onboard("comercial@seo.example", Role.COMERCIAL)
    return Fixture(console, admin, soporte, comercial)


async def get(fx: Fixture, path: str, who: Session | None = None) -> Any:
    res = await fx.console.http.get(f"{API}{path}", headers=(who or fx.comercial).auth)
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------------ definiciones


def test_percentile_nearest_rank() -> None:
    assert percentile([], 0.5) is None
    assert percentile([7], 0.9) == 7
    assert percentile([1000, 2000, 3000, 5000], 0.5) == 2000
    assert percentile([1000, 2000, 3000, 5000], 0.9) == 5000
    assert percentile([3, 1, 2], 0.5) == 2


async def test_definitions_are_exposed_for_tooltips(fx: Fixture) -> None:
    items = await get(fx, "/metric-definitions")
    assert {i["key"] for i in items} == {m.key for m in METRICS}
    assert all(i["definition"] for i in items)


# ------------------------------------------------------------------ métricas del cliente


async def test_totals_follow_the_definitions(fx: Fixture) -> None:
    data = await seed(fx)
    body = await get(fx, f"/clients/{data.client_id}/metrics")
    t = body["totals"]

    assert t["turns"] == 5  # incluye error, interrumpido y truncado; excluye otro cliente y viejo
    assert t["active_users"] == 3
    assert t["conversations"] == 2  # la de noviembre queda fuera del período
    assert t["entering_users"] == 4  # u1 entra dos veces: cuenta una
    assert t["adoption"] == pytest.approx(0.75)
    assert t["tokens"] == 150 + 10 + 400 + 25 + 600
    assert Decimal(t["cost_usd"]) == Decimal("0.031500")
    assert t["turns_without_price"] == 1  # t3 sin precio: no se estima
    assert Decimal(t["cost_per_active_user"]) == Decimal("0.010500")
    assert t["turns_with_error"] == 1
    assert t["turns_interrupted"] == 1
    assert t["turns_truncated"] == 1
    assert t["error_rate"] == pytest.approx(0.2)
    assert t["latency_p50_ms"] == 2000
    assert t["latency_p90_ms"] == 5000
    assert t["free_queries"] == 4
    assert t["free_queries_failed"] == 1


async def test_daily_series_uses_bogota_time_zone(fx: Fixture) -> None:
    data = await seed(fx)
    body = await get(fx, f"/clients/{data.client_id}/metrics")
    series = {p["day"]: p for p in body["series"]}
    assert list(series) == ["2025-12-30", "2025-12-31", "2026-01-01"]

    d30 = series["2025-12-30"]
    assert d30["turns"] == 3  # t1, t2 y t3 (23:59:59 en Bogotá)
    assert d30["active_users"] == 2
    assert d30["tokens"] == 560
    assert Decimal(d30["cost_usd"]) == Decimal("0.011000")
    assert d30["turns_with_error"] == 1
    assert d30["latency_p50_ms"] == 2000
    assert d30["latency_p90_ms"] == 3000

    d31 = series["2025-12-31"]  # t4 a las 00:00:00 en Bogotá
    assert d31["turns"] == 1
    assert d31["latency_p50_ms"] is None  # sin latencia informada

    d01 = series["2026-01-01"]
    assert d01["turns"] == 1
    assert d01["latency_p90_ms"] == 5000


async def test_breakdowns(fx: Fixture) -> None:
    data = await seed(fx)
    body = await get(fx, f"/clients/{data.client_id}/metrics")

    models = body["by_model"]
    assert [(m["provider"], m["model"], m["turns"]) for m in models] == [
        ("claude", "sonnet", 3),
        ("openai", "luna", 2),
    ]
    assert models[0]["tokens"] == 760
    assert Decimal(models[0]["cost_usd"]) == Decimal("0.031000")

    databases = {d["name"]: d for d in body["by_database"]}
    # El nombre sale del snapshot más reciente de cada base.
    assert databases["Sede Norte (nuevo nombre)"]["turns"] == 3
    assert databases["Sede Sur"]["turns"] == 2

    tools = {(t["name"], t["tipo"]): t for t in body["tools"]}
    assert tools[("consultar_datos", None)]["uses"] == 3
    assert tools[("consultar_datos", None)]["errors"] == 1
    assert tools[("consultar_conocimiento", "modulo")]["uses"] == 2
    assert tools[("consultar_conocimiento", "modulo")]["errors"] == 0

    assert body["finish_reasons"] == {
        "complete": 2,
        "error": 1,
        "interrupted": 1,
        "truncated": 1,
    }


async def test_period_filter(fx: Fixture) -> None:
    data = await seed(fx)
    body = await get(
        fx,
        f"/clients/{data.client_id}/metrics?start=2025-12-31T05:00:00Z&end=2026-01-02T00:00:00Z",
    )
    assert body["totals"]["turns"] == 2  # t4 y t5
    wide = await get(
        fx,
        f"/clients/{data.client_id}/metrics?start=2025-10-01T00:00:00Z&end=2026-01-02T00:00:00Z",
    )
    assert wide["totals"]["turns"] == 6  # suma el turno de noviembre


async def test_users_ranking_is_pseudonymous(fx: Fixture) -> None:
    data = await seed(fx)
    users = await get(fx, f"/clients/{data.client_id}/users")
    assert [u["user_ref"] for u in users] == ["u1", "u2", "u3"]
    assert users[0]["turns"] == 2
    assert Decimal(users[0]["cost_usd"]) == Decimal("0.011000")
    assert users[0]["databases_used"] == 1
    assert set(users[0]) == {"user_ref", "turns", "cost_usd", "last_used_at", "databases_used"}


async def test_databases_show_latest_snapshot(fx: Fixture) -> None:
    data = await seed(fx)
    databases = await get(fx, f"/clients/{data.client_id}/databases")
    assert [d["name"] for d in databases] == ["Sede Norte (nuevo nombre)", "Sede Sur"]
    assert databases[0]["snapshot_date"] == "2025-12-31"


async def test_unknown_client_is_404(fx: Fixture) -> None:
    res = await fx.console.http.get(f"{API}/clients/{uuid4()}/metrics", headers=fx.admin.auth)
    assert res.status_code == 404
    assert res.json()["errorCode"] == "client_not_found"


# ------------------------------------------------------------------ resumen y frescura


async def test_overview_aggregates_all_clients(fx: Fixture) -> None:
    data = await seed(fx)
    linked = await link_instance(fx, data.client_id)
    await heartbeat_with_sync(fx, linked, watermark="2026-01-01T11:00:00Z")

    body = await get(fx, "/overview")
    assert body["clients"] == {"active": 2, "suspended": 0}
    assert body["instances"] == {"online": 1, "offline": 0, "suspended": 0, "revoked": 0}
    # Otro cliente suma: 5 turnos de FARMX + 1 de OTRO1.
    assert body["usage"]["turns"] == 6
    assert body["usage"]["active_users"] == 4
    assert [(p["provider"], p["turns"]) for p in body["providers"]] == [
        ("claude", 4),
        ("openai", 2),
    ]
    assert body["versions"] == [{"version": "v1.1.0", "instances": 1}]
    assert len(body["trend"]) == 3


async def heartbeat_with_sync(fx: Fixture, who: Linked, *, watermark: str) -> None:
    res = await fx.console.http.post(
        "/api/v1/instances/heartbeat",
        json={
            "sent_at": fx.console.clock.now.isoformat(),
            "fingerprint": "fp-1",
            "version": "v1.1.0",
            "deployment_mode": "server",
            "sync": {
                "streams": {"turn": {"watermark_at": watermark, "last_ok_at": watermark}},
                "last_error": None,
            },
        },
        headers=who.auth,
    )
    assert res.status_code == 200, res.text


async def test_freshness_is_the_worst_of_contact_and_stream_watermark(fx: Fixture) -> None:
    client_id = await make_client(fx)
    empty = await get(fx, f"/clients/{client_id}/metrics")
    assert empty["freshness"] == {"seconds": None, "last_seen_at": None}

    linked = await link_instance(fx, client_id)
    await heartbeat_with_sync(fx, linked, watermark="2026-01-01T11:00:00Z")
    now = await get(fx, f"/clients/{client_id}/metrics")
    assert now["freshness"]["seconds"] == 3600  # contacto: 0 s; marca del stream: 1 h

    fx.console.clock.advance(minutes=10)
    session = await fx.console.login("comercial@seo.example")
    later = await get(fx, f"/clients/{client_id}/metrics", session)
    # 1 h desde la marca + 10 min + 31 s que avanza el ingreso del helper.
    assert later["freshness"]["seconds"] == 3600 + 600 + 31


async def test_metrics_require_read_permission_only(fx: Fixture) -> None:
    data = await seed(fx)
    for who in (fx.admin, fx.soporte, fx.comercial):
        res = await fx.console.http.get(f"{API}/clients/{data.client_id}/metrics", headers=who.auth)
        assert res.status_code == 200
    anonymous = await fx.console.http.get(f"{API}/clients/{data.client_id}/metrics")
    assert anonymous.status_code == 401
