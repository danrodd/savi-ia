"""Puesta en marcha de un cliente: avance en una sola petición (`/clients/{id}/onboarding`)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.staff.domain import Role
from tests.console_helpers import ConsoleEnv
from tests.test_console_api import API, Fixture, heartbeat, link_instance, make_client
from tests.test_console_policy import send, session_event

NOTHING = {
    "plan_loaded": False,
    "policy_defined": False,
    "ai_defined": False,
    "token_created": False,
    "instance_connected": False,
    "report_received": False,
}


@pytest.fixture
async def fx(console: ConsoleEnv) -> Fixture:
    admin = await console.onboard("admin@seo.example", Role.ADMIN)
    soporte = await console.onboard("soporte@seo.example", Role.SOPORTE)
    comercial = await console.onboard("comercial@seo.example", Role.COMERCIAL)
    return Fixture(console, admin, soporte, comercial)


async def onboarding(fx: Fixture, client_id: str, who: str = "soporte") -> dict[str, bool]:
    session = getattr(fx, who)
    res = await fx.console.http.get(f"{API}/clients/{client_id}/onboarding", headers=session.auth)
    assert res.status_code == 200, res.text
    return dict(res.json())


async def test_new_client_has_nothing_done(fx: Fixture) -> None:
    client_id = await make_client(fx)

    assert await onboarding(fx, client_id) == NOTHING


async def test_unknown_client_is_404(fx: Fixture) -> None:
    res = await fx.console.http.get(f"{API}/clients/{uuid4()}/onboarding", headers=fx.admin.auth)

    assert res.status_code == 404


async def test_plan_counts_with_plan_name_or_validity_but_not_only_notes(fx: Fixture) -> None:
    client_id = await make_client(fx)
    url = f"{API}/clients/{client_id}/subscription"
    notes = await fx.console.http.put(
        url, json={"notes": "solo una nota"}, headers=fx.comercial.auth
    )
    assert notes.status_code == 200, notes.text
    assert (await onboarding(fx, client_id))["plan_loaded"] is False

    await fx.console.http.put(url, json={"plan_name": "Pro"}, headers=fx.comercial.auth)

    # Otro rol (soporte) lo ve aunque no pueda abrir la suscripción.
    assert (await onboarding(fx, client_id, "soporte"))["plan_loaded"] is True


async def test_policy_counts_when_saved_even_with_default_values(fx: Fixture) -> None:
    client_id = await make_client(fx)
    saved = await fx.console.http.patch(
        f"{API}/clients/{client_id}/policy",
        json={"config_locked": False},
        headers=fx.admin.auth,
    )
    assert saved.status_code == 200, saved.text

    state = await onboarding(fx, client_id)

    assert state["policy_defined"] is True
    assert state["ai_defined"] is False


async def test_policy_counts_when_it_differs_from_the_defaults(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await fx.console.http.patch(
        f"{API}/clients/{client_id}/policy", json={"config_locked": True}, headers=fx.admin.auth
    )

    assert (await onboarding(fx, client_id))["policy_defined"] is True


async def test_ai_limits_count_when_saved_even_empty(fx: Fixture) -> None:
    client_id = await make_client(fx)
    saved = await fx.console.http.put(
        f"{API}/clients/{client_id}/ai-policy", json={}, headers=fx.admin.auth
    )
    assert saved.status_code == 200, saved.text

    assert (await onboarding(fx, client_id))["ai_defined"] is True


async def test_ai_limits_count_with_a_cap(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await fx.console.http.put(
        f"{API}/clients/{client_id}/ai-policy",
        json={"user_monthly_usd": "5"},
        headers=fx.admin.auth,
    )

    assert (await onboarding(fx, client_id))["ai_defined"] is True


async def test_token_installation_and_report_steps_follow_the_real_flow(fx: Fixture) -> None:
    client_id = await make_client(fx)
    created = await fx.console.http.post(
        f"{API}/clients/{client_id}/enrollment-tokens", json={}, headers=fx.soporte.auth
    )
    assert created.status_code == 201, created.text
    assert (await onboarding(fx, client_id))["token_created"] is True

    # Un token revocado sigue contando: el paso es "alguna vez se generó".
    await fx.console.http.delete(
        f"{API}/enrollment-tokens/{created.json()['id']}", headers=fx.soporte.auth
    )
    assert (await onboarding(fx, client_id))["token_created"] is True

    other = await make_client(fx, "OTRO", "Otro cliente")
    linked = await link_instance(fx, other)
    assert (await onboarding(fx, other))["instance_connected"] is False

    assert (await heartbeat(fx, linked)).status_code == 200
    state = await onboarding(fx, other)
    assert state["instance_connected"] is True
    assert state["report_received"] is False

    await send(fx, linked, [session_event("s-1", "a" * 32)])
    assert (await onboarding(fx, other))["report_received"] is True
    # Lo de un cliente no cuenta para otro.
    assert (await onboarding(fx, client_id))["instance_connected"] is False
