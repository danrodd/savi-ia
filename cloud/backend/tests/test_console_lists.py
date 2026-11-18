"""Listas de la consola con datos de negocio: consumo, plan y salud de cada cliente."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.alerts.infrastructure import AlertModel
from app.modules.staff.domain import Role
from tests.console_helpers import ConsoleEnv
from tests.test_console_api import API, Fixture, link_instance, make_client
from tests.test_console_metrics import DB_A, _turn  # pyright: ignore[reportPrivateUsage]


@pytest.fixture
async def fx(console: ConsoleEnv) -> Fixture:
    admin = await console.onboard("admin@seo.example", Role.ADMIN)
    soporte = await console.onboard("soporte@seo.example", Role.SOPORTE)
    comercial = await console.onboard("comercial@seo.example", Role.COMERCIAL)
    return Fixture(console, admin, soporte, comercial)


async def add_turns(
    fx: Fixture, client_id: str, count: int, *, instance: str | None = None
) -> None:
    at = fx.console.clock.now - timedelta(days=1)
    async with fx.console.maker() as s, s.begin():
        for n in range(count):
            row = _turn(
                UUID(client_id),
                f"{client_id[:8]}-{n}",
                at.isoformat(),
                f"u{n % 2}",
                "claude",
                "sonnet",
                "complete",
                (1, 1, 0, 0),
                "0.250000",
                10,
                DB_A,
                [],
            )
            if instance is not None:
                row.instance_id = UUID(instance)
            s.add(row)


async def add_alert(fx: Fixture, client_id: str, severity: str) -> None:
    async with fx.console.maker() as s, s.begin():
        s.add(
            AlertModel(
                id=uuid4(),
                rule_code="cost_spike",
                severity=severity,
                client_id=UUID(client_id),
                instance_id=None,
                status="open",
                details={},
                opened_at=fx.console.clock.now,
                dedup_key=f"cost_spike:{client_id}",
            )
        )


async def clients(fx: Fixture, query: str = "", who: Any = None) -> list[dict[str, Any]]:
    res = await fx.console.http.get(f"{API}/clients{query}", headers=(who or fx.comercial).auth)
    assert res.status_code == 200, res.text
    return list(res.json()["items"])


async def test_clients_carry_their_usage_of_the_last_30_days(fx: Fixture) -> None:
    busy = await make_client(fx, "BUSY1", "Mucho uso")
    await make_client(fx, "QUIET", "Sin uso")
    await add_turns(fx, busy, 4)

    rows = {c["code"]: c for c in await clients(fx)}
    assert rows["BUSY1"]["turns_30d"] == 4
    assert rows["BUSY1"]["active_users_30d"] == 2
    assert rows["BUSY1"]["cost_30d_usd"] == "1.000000"
    assert rows["QUIET"]["turns_30d"] == 0
    assert rows["QUIET"]["health"] == "ok"


async def test_attention_sort_puts_problems_first_then_usage(fx: Fixture) -> None:
    calm = await make_client(fx, "AAAA1", "Tranquilo con uso")
    await make_client(fx, "BBBB1", "Tranquilo sin uso")
    alarm = await make_client(fx, "ZZZZ1", "Con alerta crítica")
    waiting = await make_client(fx, "YYYY1", "Esperando conexión")
    await add_turns(fx, calm, 3)
    await add_alert(fx, alarm, "critical")
    await link_instance(fx, waiting)

    rows = await clients(fx)
    assert [c["code"] for c in rows] == ["ZZZZ1", "YYYY1", "AAAA1", "BBBB1"]
    by_code = {c["code"]: c for c in rows}
    assert by_code["ZZZZ1"]["health"] == "critical"
    assert by_code["ZZZZ1"]["open_alerts"] == {"critical": 1}
    assert by_code["YYYY1"]["health"] == "info"
    assert by_code["YYYY1"]["instances_waiting"] == 1

    by_usage = await clients(fx, "?sort=usage")
    assert by_usage[0]["code"] == "AAAA1"


async def test_plan_is_only_visible_with_billing_permission(fx: Fixture) -> None:
    client = await make_client(fx, "PLAN1", "Con plan")
    expired = (fx.console.clock.now - timedelta(days=3)).date().isoformat()
    res = await fx.console.http.put(
        f"{API}/clients/{client}/subscription",
        json={"plan_name": "Empresarial", "max_users": 20, "valid_until": expired},
        headers=fx.comercial.auth,
    )
    assert res.status_code == 200, res.text

    seen_by_sales = (await clients(fx))[0]
    assert seen_by_sales["plan"] == {
        "name": "Empresarial",
        "max_users": 20,
        "valid_until": expired,
        "status": "expired",
    }
    assert seen_by_sales["health"] == "critical"

    # Soporte no ve facturación: ni el plan ni su efecto en la salud.
    seen_by_support = (await clients(fx, who=fx.soporte))[0]
    assert seen_by_support["plan"] is None
    assert seen_by_support["health"] == "ok"


async def test_instances_carry_their_own_turns(fx: Fixture) -> None:
    client = await make_client(fx)
    linked = await link_instance(fx, client)
    await add_turns(fx, client, 2, instance=linked.instance_id)
    await add_turns(fx, await make_client(fx, "OTRO1", "Otro"), 5)

    res = await fx.console.http.get(f"{API}/instances", headers=fx.soporte.auth)
    assert res.status_code == 200, res.text
    assert [(i["client_code"], i["turns_30d"]) for i in res.json()] == [("FARMX", 2)]


async def test_people_get_a_stable_number_by_first_appearance(fx: Fixture) -> None:
    client = await make_client(fx)
    linked = await link_instance(fx, client)
    now = fx.console.clock.now
    async with fx.console.maker() as s, s.begin():
        # u-late aparece después que u-early, aunque su seudónimo ordene antes.
        for source, user, days in (("p1", "b-early", 5), ("p2", "a-late", 2), ("p3", "b-early", 1)):
            row = _turn(
                UUID(client),
                source,
                (now - timedelta(days=days)).isoformat(),
                user,
                "claude",
                "sonnet",
                "complete",
                (1, 1, 0, 0),
                "0.100000",
                10,
                DB_A,
                [],
            )
            row.instance_id = UUID(linked.instance_id)
            s.add(row)

    res = await fx.console.http.get(f"{API}/clients/{client}/users", headers=fx.comercial.auth)
    numbers = {u["user_ref"]: u["number"] for u in res.json()}
    assert numbers == {"b-early": 1, "a-late": 2}

    people = await fx.console.http.get(f"{API}/clients/{client}/people", headers=fx.comercial.auth)
    assert {p["user_ref"]: p["number"] for p in people.json()} == numbers


async def test_instance_metrics_only_count_that_installation(fx: Fixture) -> None:
    client = await make_client(fx)
    first = await link_instance(fx, client, fingerprint="fp-1")
    second = await link_instance(fx, client, fingerprint="fp-2")
    await add_turns(fx, client, 3, instance=first.instance_id)
    async with fx.console.maker() as s, s.begin():
        row = _turn(
            UUID(client),
            "other",
            (fx.console.clock.now - timedelta(days=1)).isoformat(),
            "u9",
            "claude",
            "sonnet",
            "error",
            (1, 1, 0, 0),
            "1.000000",
            10,
            DB_A,
            [],
        )
        row.instance_id = UUID(second.instance_id)
        s.add(row)

    res = await fx.console.http.get(
        f"{API}/instances/{first.instance_id}/metrics", headers=fx.soporte.auth
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["totals"]["turns"] == 3
    assert body["totals"]["cost_usd"] == "0.750000"
    assert sum(d["turns"] for d in body["series"]) == 3

    listed = await fx.console.http.get(f"{API}/instances", headers=fx.soporte.auth)
    by_id = {i["id"]: i for i in listed.json()}
    assert by_id[second.instance_id]["errors_30d"] == 1
    assert by_id[second.instance_id]["cost_30d_usd"] == "1.000000"
    assert by_id[first.instance_id]["errors_30d"] == 0


async def test_instance_metrics_of_unknown_instance_is_404(fx: Fixture) -> None:
    res = await fx.console.http.get(f"{API}/instances/{uuid4()}/metrics", headers=fx.soporte.auth)
    assert res.status_code == 404
