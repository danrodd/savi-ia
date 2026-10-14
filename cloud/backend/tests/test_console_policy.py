"""Política por cliente (M2): bloqueo de configuración, identidad y etiquetas de persona."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.staff.domain import Role
from tests.console_helpers import ConsoleEnv
from tests.test_console_api import (
    API,
    Fixture,
    Linked,
    heartbeat,
    link_instance,
    make_client,
)

INGEST = "/api/v1/instances/ingest"
USER_A = "a" * 32
USER_B = "b" * 32
DATABASE = "7a1f3c52-9d4e-4b6a-8c0d-1e2f3a4b5c6d"


@pytest.fixture
async def fx(console: ConsoleEnv) -> Fixture:
    admin = await console.onboard("admin@seo.example", Role.ADMIN)
    soporte = await console.onboard("soporte@seo.example", Role.SOPORTE)
    comercial = await console.onboard("comercial@seo.example", Role.COMERCIAL)
    return Fixture(console, admin, soporte, comercial)


def session_event(source: str, user_ref: str, label: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {"user_ref": user_ref, "database_ref": DATABASE}
    if label is not None:
        data["user_label"] = label
    return {
        "schema": "session/1",
        "source_id": source,
        "occurred_at": "2026-01-01T11:00:00Z",
        "data": data,
    }


async def send(fx: Fixture, who: Linked, events: list[dict[str, Any]]) -> dict[str, Any]:
    res = await fx.console.http.post(
        INGEST,
        json={
            "batch_id": str(uuid4()),
            "sent_at": fx.console.clock.now.isoformat(),
            "events": events,
        },
        headers=who.auth,
    )
    assert res.status_code == 200, res.text
    return dict(res.json())


async def stored_labels(fx: Fixture) -> dict[str, str | None]:
    async with fx.console.maker() as s:
        rows = await s.execute(text("SELECT source_id, user_label FROM ev_sessions"))
        return {r[0]: r[1] for r in rows}


# ------------------------------------------------------------------ política hacia la instancia
async def test_default_policy_is_pseudonymous_and_unlocked(fx: Fixture) -> None:
    linked = await link_instance(fx, await make_client(fx))

    policy = (await heartbeat(fx, linked)).json()["policy"]

    assert policy["config_locked"] is False
    assert policy["identity_mode"] == "pseudonym"


async def test_policy_travels_in_the_heartbeat_and_in_the_enrollment(fx: Fixture) -> None:
    client_id = await make_client(fx)
    set_policy = await fx.console.http.patch(
        f"{API}/clients/{client_id}/policy",
        json={"config_locked": True, "identity_mode": "named"},
        headers=fx.admin.auth,
    )
    assert set_policy.status_code == 200
    assert set_policy.json()["config_locked"] is True
    assert set_policy.json()["identity_mode"] == "named"

    # Una instalación nueva ya nace con la política (respuesta del canje del token).
    token = (
        await fx.console.http.post(
            f"{API}/clients/{client_id}/enrollment-tokens", json={}, headers=fx.soporte.auth
        )
    ).json()["token"]
    enrolled = await fx.console.http.post(
        "/api/v1/enrollments/redeem",
        json={
            "token": token,
            "instance": {
                "name": "PC-ANA",
                "deployment_mode": "desktop",
                "os": "Windows 11",
                "agent_db_engine": "sqlite",
                "fingerprint": "fp-ana",
            },
        },
    )
    assert enrolled.json()["policy"]["config_locked"] is True
    assert enrolled.json()["policy"]["identity_mode"] == "named"

    secret = enrolled.json()["instance_secret"]
    beat = await fx.console.http.post(
        "/api/v1/instances/heartbeat",
        json={
            "sent_at": fx.console.clock.now.isoformat(),
            "fingerprint": "fp-ana",
            "version": "v1.2.0",
            "deployment_mode": "desktop",
        },
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert beat.json()["policy"]["config_locked"] is True
    assert beat.json()["policy"]["identity_mode"] == "named"


async def test_allow_local_cli_is_off_by_default_and_travels_in_the_heartbeat(
    fx: Fixture,
) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)
    assert (await heartbeat(fx, linked)).json()["policy"]["allow_local_cli"] is False

    res = await fx.console.http.patch(
        f"{API}/clients/{client_id}/policy",
        json={"allow_local_cli": True},
        headers=fx.admin.auth,
    )

    assert res.status_code == 200
    assert res.json()["allow_local_cli"] is True
    assert (await heartbeat(fx, linked)).json()["policy"]["allow_local_cli"] is True


async def test_only_admin_can_change_the_policy(fx: Fixture) -> None:
    client_id = await make_client(fx)
    for who in (fx.soporte, fx.comercial):
        res = await fx.console.http.patch(
            f"{API}/clients/{client_id}/policy", json={"config_locked": True}, headers=who.auth
        )
        assert res.status_code == 403


async def test_policy_changes_are_audited(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await fx.console.http.patch(
        f"{API}/clients/{client_id}/policy",
        json={"identity_mode": "named"},
        headers=fx.admin.auth,
    )

    audit = (
        await fx.console.http.get(f"{API}/audit?action=client.policy", headers=fx.admin.auth)
    ).json()

    entry = audit["items"][0]
    assert entry["before"]["identity_mode"] == "pseudonym"
    assert entry["after"]["identity_mode"] == "named"
    assert entry["actor_email"] == "admin@seo.example"


async def test_partial_policy_update_keeps_the_other_field(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await fx.console.http.patch(
        f"{API}/clients/{client_id}/policy", json={"config_locked": True}, headers=fx.admin.auth
    )

    res = await fx.console.http.patch(
        f"{API}/clients/{client_id}/policy", json={"identity_mode": "named"}, headers=fx.admin.auth
    )

    assert res.json()["config_locked"] is True
    assert res.json()["identity_mode"] == "named"


async def test_invalid_identity_mode_is_rejected(fx: Fixture) -> None:
    client_id = await make_client(fx)
    res = await fx.console.http.patch(
        f"{API}/clients/{client_id}/policy", json={"identity_mode": "todos"}, headers=fx.admin.auth
    )
    assert res.status_code == 422


# ------------------------------------------------------------------ etiquetas de persona
async def test_labels_are_dropped_for_pseudonymous_clients(fx: Fixture) -> None:
    """Una instancia que manda etiquetas a un cliente que no las autorizó: Cloud las descarta."""
    linked = await link_instance(fx, await make_client(fx))

    answer = await send(fx, linked, [session_event("s1", USER_A, label="JPEREZ")])

    assert answer["accepted"] == 1  # el evento entra; solo se pierde la etiqueta
    assert (await stored_labels(fx)) == {"s1": None}


async def test_labels_are_kept_for_named_clients(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await fx.console.http.patch(
        f"{API}/clients/{client_id}/policy", json={"identity_mode": "named"}, headers=fx.admin.auth
    )
    linked = await link_instance(fx, client_id)

    await send(fx, linked, [session_event("s1", USER_A, label="JPEREZ")])

    assert (await stored_labels(fx)) == {"s1": "JPEREZ"}


async def test_people_of_an_instance_with_labels(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await fx.console.http.patch(
        f"{API}/clients/{client_id}/policy", json={"identity_mode": "named"}, headers=fx.admin.auth
    )
    linked = await link_instance(fx, client_id)
    await send(
        fx,
        linked,
        [
            session_event("s1", USER_A, label="JPEREZ"),
            session_event("s2", USER_A, label="JPEREZ"),
            session_event("s3", USER_B, label="MGOMEZ"),
        ],
    )

    people = (
        await fx.console.http.get(
            f"{API}/instances/{linked.instance_id}/people", headers=fx.comercial.auth
        )
    ).json()

    by_label = {p["label"]: p for p in people}
    assert set(by_label) == {"JPEREZ", "MGOMEZ"}
    assert by_label["JPEREZ"]["sessions"] == 2
    assert by_label["MGOMEZ"]["sessions"] == 1


async def test_people_have_no_label_for_pseudonymous_clients(fx: Fixture) -> None:
    linked = await link_instance(fx, await make_client(fx))
    await send(fx, linked, [session_event("s1", USER_A, label="JPEREZ")])

    people = (
        await fx.console.http.get(
            f"{API}/instances/{linked.instance_id}/people", headers=fx.admin.auth
        )
    ).json()

    assert [p["label"] for p in people] == [None]
    assert people[0]["user_ref"] == USER_A


async def test_people_of_unknown_instance_is_404(fx: Fixture) -> None:
    res = await fx.console.http.get(f"{API}/instances/{uuid4()}/people", headers=fx.admin.auth)
    assert res.status_code == 404
    assert res.json()["errorCode"] == "instance_not_found"


async def test_label_longer_than_the_contract_is_rejected_per_event(fx: Fixture) -> None:
    linked = await link_instance(fx, await make_client(fx))

    answer = await send(fx, linked, [session_event("s1", USER_A, label="X" * 65)])

    assert answer["accepted"] == 0
    assert answer["rejected"] == [{"source_id": "s1", "reason": "invalid_event"}]
