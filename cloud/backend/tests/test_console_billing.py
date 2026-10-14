"""Suscripción y movimientos por cliente (M5-A): se registran a mano, vencen y alertan."""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.alerts.runner import run_evaluation
from app.modules.staff.domain import Role
from tests.console_helpers import ConsoleEnv
from tests.test_console_api import API, Fixture, make_client

TODAY = "2026-01-01"


@pytest.fixture
async def fx(console: ConsoleEnv) -> Fixture:
    admin = await console.onboard("admin@seo.example", Role.ADMIN)
    soporte = await console.onboard("soporte@seo.example", Role.SOPORTE)
    comercial = await console.onboard("comercial@seo.example", Role.COMERCIAL)
    return Fixture(console, admin, soporte, comercial)


async def put_subscription(fx: Fixture, client_id: str, **body: Any) -> Any:
    return await fx.console.http.put(
        f"{API}/clients/{client_id}/subscription", json=body, headers=fx.comercial.auth
    )


async def live_codes(fx: Fixture) -> list[tuple[str, str]]:
    await run_evaluation(fx.console.maker, fx.console.app.state.settings, fx.console.clock)
    res = await fx.console.http.get(f"{API}/alerts", headers=fx.admin.auth)
    return sorted((a["rule_code"], a["severity"]) for a in res.json() if a["status"] != "resolved")


# ------------------------------------------------------------------ plan


async def test_new_client_has_no_subscription(fx: Fixture) -> None:
    client_id = await make_client(fx)

    res = await fx.console.http.get(
        f"{API}/clients/{client_id}/subscription", headers=fx.comercial.auth
    )

    assert res.status_code == 200
    assert res.json()["status"] == "none"
    assert res.json()["plan_name"] is None


async def test_set_subscription_computes_status_and_days_left(fx: Fixture) -> None:
    client_id = await make_client(fx)

    res = await put_subscription(
        fx,
        client_id,
        plan_name="Equipo",
        monthly_fee_usd="120.50",
        max_users=10,
        valid_until="2026-01-31",
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["plan_name"] == "Equipo"
    assert body["monthly_fee_usd"] == "120.50"
    assert body["max_users"] == 10
    assert body["status"] == "active"
    assert body["days_left"] == 30


async def test_status_is_expiring_inside_the_window_and_expired_after(fx: Fixture) -> None:
    client_id = await make_client(fx)

    soon = await put_subscription(fx, client_id, valid_until="2026-01-05")
    gone = await put_subscription(fx, client_id, valid_until="2025-12-30")

    assert soon.json()["status"] == "expiring"
    assert gone.json()["status"] == "expired"
    assert gone.json()["days_left"] == -2


async def test_negative_fee_and_empty_plan_name_are_rejected_or_cleaned(fx: Fixture) -> None:
    client_id = await make_client(fx)

    negative = await put_subscription(fx, client_id, monthly_fee_usd="-1")
    blank = await put_subscription(fx, client_id, plan_name="   ", valid_until="2026-02-01")

    assert negative.status_code == 422
    assert blank.status_code == 200
    assert blank.json()["plan_name"] is None


# ------------------------------------------------------------------ permisos


async def test_support_cannot_see_or_change_billing(fx: Fixture) -> None:
    client_id = await make_client(fx)

    read = await fx.console.http.get(
        f"{API}/clients/{client_id}/subscription", headers=fx.soporte.auth
    )
    write = await fx.console.http.put(
        f"{API}/clients/{client_id}/subscription", json={}, headers=fx.soporte.auth
    )
    ledger = await fx.console.http.get(f"{API}/clients/{client_id}/ledger", headers=fx.soporte.auth)

    assert (read.status_code, write.status_code, ledger.status_code) == (403, 403, 403)


async def test_unknown_client_is_404(fx: Fixture) -> None:
    missing = "00000000-0000-0000-0000-000000000000"

    sub = await fx.console.http.get(
        f"{API}/clients/{missing}/subscription", headers=fx.comercial.auth
    )
    ledger = await fx.console.http.get(f"{API}/clients/{missing}/ledger", headers=fx.comercial.auth)

    assert (sub.status_code, ledger.status_code) == (404, 404)


# ------------------------------------------------------------------ movimientos


async def test_payment_is_recorded_and_extends_validity(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await put_subscription(fx, client_id, valid_until="2026-01-03")

    res = await fx.console.http.post(
        f"{API}/clients/{client_id}/ledger",
        json={
            "kind": "payment",
            "amount_usd": "120.50",
            "note": "Transferencia 4412",
            "extends_until": "2026-02-03",
        },
        headers=fx.comercial.auth,
    )

    assert res.status_code == 201, res.text
    assert res.json()["created_by"] == "comercial@seo.example"
    sub = await fx.console.http.get(
        f"{API}/clients/{client_id}/subscription", headers=fx.comercial.auth
    )
    assert sub.json()["valid_until"] == "2026-02-03"
    listed = await fx.console.http.get(f"{API}/clients/{client_id}/ledger", headers=fx.admin.auth)
    assert [(e["kind"], e["amount_usd"]) for e in listed.json()] == [("payment", "120.50")]


async def test_a_payment_never_shortens_the_validity(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await put_subscription(fx, client_id, valid_until="2026-06-01")

    await fx.console.http.post(
        f"{API}/clients/{client_id}/ledger",
        json={
            "kind": "payment",
            "amount_usd": "10",
            "note": "Pago atrasado",
            "extends_until": "2026-02-01",
        },
        headers=fx.comercial.auth,
    )

    sub = await fx.console.http.get(
        f"{API}/clients/{client_id}/subscription", headers=fx.comercial.auth
    )
    assert sub.json()["valid_until"] == "2026-06-01"


async def test_ledger_validations(fx: Fixture) -> None:
    client_id = await make_client(fx)
    url = f"{API}/clients/{client_id}/ledger"

    zero = await fx.console.http.post(
        url, json={"kind": "payment", "amount_usd": "0", "note": "x"}, headers=fx.comercial.auth
    )
    negative_payment = await fx.console.http.post(
        url, json={"kind": "payment", "amount_usd": "-5", "note": "x"}, headers=fx.comercial.auth
    )
    no_note = await fx.console.http.post(
        url, json={"kind": "payment", "amount_usd": "5", "note": "   "}, headers=fx.comercial.auth
    )
    negative_adjustment = await fx.console.http.post(
        url,
        json={"kind": "adjustment", "amount_usd": "-5", "note": "Devolución"},
        headers=fx.comercial.auth,
    )

    assert zero.status_code == 422
    assert negative_payment.status_code == 422
    assert no_note.status_code == 422
    assert negative_adjustment.status_code == 201


async def test_ledger_lists_newest_first(fx: Fixture) -> None:
    client_id = await make_client(fx)
    for n, amount in enumerate(("10", "20", "30")):
        fx.console.clock.advance(minutes=1)
        await fx.console.http.post(
            f"{API}/clients/{client_id}/ledger",
            json={"kind": "payment", "amount_usd": amount, "note": f"pago {n}"},
            headers=fx.comercial.auth,
        )

    res = await fx.console.http.get(f"{API}/clients/{client_id}/ledger", headers=fx.admin.auth)

    assert [e["amount_usd"] for e in res.json()] == ["30.00", "20.00", "10.00"]


async def test_changes_are_audited(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await put_subscription(fx, client_id, plan_name="Equipo", valid_until="2026-02-01")
    await fx.console.http.post(
        f"{API}/clients/{client_id}/ledger",
        json={"kind": "payment", "amount_usd": "50", "note": "Pago"},
        headers=fx.comercial.auth,
    )

    res = await fx.console.http.get(f"{API}/audit", headers=fx.admin.auth)

    actions = {row["action"] for row in res.json()["items"]}
    assert {"client.subscription", "client.ledger_entry"} <= actions


# ------------------------------------------------------------------ alertas


async def test_alert_opens_inside_window_escalates_and_resolves_on_payment(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await put_subscription(fx, client_id, valid_until="2026-01-20")
    assert await live_codes(fx) == []

    await put_subscription(fx, client_id, valid_until="2026-01-05")
    assert await live_codes(fx) == [("subscription_due", "warning")]

    await put_subscription(fx, client_id, valid_until="2025-12-31")
    assert await live_codes(fx) == [("subscription_due", "critical")]

    await fx.console.http.post(
        f"{API}/clients/{client_id}/ledger",
        json={
            "kind": "payment",
            "amount_usd": "100",
            "note": "Renovación",
            "extends_until": "2026-03-01",
        },
        headers=fx.comercial.auth,
    )
    assert await live_codes(fx) == []


async def test_internal_organization_is_not_billed(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await fx.console.http.patch(
        f"{API}/clients/{client_id}/policy",
        json={"identity_mode": "named"},
        headers=fx.admin.auth,
    )
    await put_subscription(fx, client_id, valid_until="2025-12-01")

    assert await live_codes(fx) == []
