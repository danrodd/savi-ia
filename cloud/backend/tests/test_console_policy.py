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


async def test_client_people_include_everyone_without_a_time_window(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await fx.console.http.patch(
        f"{API}/clients/{client_id}/policy", json={"identity_mode": "named"}, headers=fx.admin.auth
    )
    linked = await link_instance(fx, client_id)
    old = session_event("s2", USER_B, label="MGOMEZ")
    old["occurred_at"] = "2020-01-01T11:00:00Z"  # muy fuera de los últimos 30 días
    await send(fx, linked, [session_event("s1", USER_A, label="JPEREZ"), old])

    people = (
        await fx.console.http.get(f"{API}/clients/{client_id}/people", headers=fx.comercial.auth)
    ).json()

    assert [p["user_ref"] for p in people] == [USER_A, USER_B]  # la más reciente primero
    assert {p["user_ref"]: p["label"] for p in people} == {USER_A: "JPEREZ", USER_B: "MGOMEZ"}


async def test_client_people_of_unknown_client_is_404(fx: Fixture) -> None:
    res = await fx.console.http.get(f"{API}/clients/{uuid4()}/people", headers=fx.admin.auth)
    assert res.status_code == 404


async def test_people_of_unknown_instance_is_404(fx: Fixture) -> None:
    res = await fx.console.http.get(f"{API}/instances/{uuid4()}/people", headers=fx.admin.auth)
    assert res.status_code == 404
    assert res.json()["errorCode"] == "instance_not_found"


async def test_label_longer_than_the_contract_is_rejected_per_event(fx: Fixture) -> None:
    linked = await link_instance(fx, await make_client(fx))

    answer = await send(fx, linked, [session_event("s1", USER_A, label="X" * 65)])

    assert answer["accepted"] == 0
    assert answer["rejected"] == [{"source_id": "s1", "reason": "invalid_event"}]


# ------------------------------------------------------------------ política de IA (M3)
AI_BODY: dict[str, Any] = {
    "allowed_providers": ["claude", "gemini"],
    "user_monthly_usd": "5",
    "provider_monthly_usd": {"gemini": "50"},
    "user_overrides": {USER_A: "20"},
}


async def test_ai_policy_is_empty_by_default_and_not_sent(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    body = (await heartbeat(fx, linked)).json()

    assert body["policy"]["ai"] is None
    client = (await fx.console.http.get(f"{API}/clients/{client_id}", headers=fx.admin.auth)).json()
    assert client["ai_policy"]["allowed_providers"] is None
    assert client["ai_policy"]["user_monthly_usd"] is None


async def test_ai_policy_travels_in_the_heartbeat_and_matches_the_contract(fx: Fixture) -> None:
    from tests.test_api import assert_matches_schema

    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    res = await fx.console.http.put(
        f"{API}/clients/{client_id}/ai-policy", json=AI_BODY, headers=fx.admin.auth
    )

    assert res.status_code == 200, res.text
    beat = (await heartbeat(fx, linked)).json()
    assert beat["policy"]["ai"] == {
        "allowed_providers": ["claude", "gemini"],
        "user_monthly_usd": "5",
        "provider_monthly_usd": {"gemini": "50"},
        "user_overrides": {USER_A: "20"},
    }
    assert_matches_schema("heartbeat.response", beat)


async def test_ai_policy_can_be_cleared(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)
    await fx.console.http.put(
        f"{API}/clients/{client_id}/ai-policy", json=AI_BODY, headers=fx.admin.auth
    )

    await fx.console.http.put(
        f"{API}/clients/{client_id}/ai-policy", json={}, headers=fx.admin.auth
    )

    assert (await heartbeat(fx, linked)).json()["policy"]["ai"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"allowed_providers": ["otro"]},
        {"user_monthly_usd": "-1"},
        {"provider_monthly_usd": {"otro": "5"}},
        {"user_overrides": {"no-es-un-user-ref": "5"}},
        {"user_monthly_usd": "5", "campo_extra": 1},
    ],
)
async def test_invalid_ai_policy_is_rejected(fx: Fixture, body: dict[str, Any]) -> None:
    client_id = await make_client(fx)

    res = await fx.console.http.put(
        f"{API}/clients/{client_id}/ai-policy", json=body, headers=fx.admin.auth
    )

    assert res.status_code == 422, res.text


async def test_only_admin_can_change_the_ai_policy(fx: Fixture) -> None:
    client_id = await make_client(fx)
    for who in (fx.soporte, fx.comercial):
        res = await fx.console.http.put(
            f"{API}/clients/{client_id}/ai-policy", json=AI_BODY, headers=who.auth
        )
        assert res.status_code == 403


async def test_ai_policy_changes_are_audited_with_before_and_after(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await fx.console.http.put(
        f"{API}/clients/{client_id}/ai-policy", json=AI_BODY, headers=fx.admin.auth
    )

    audit = (
        await fx.console.http.get(f"{API}/audit?action=client.ai_policy", headers=fx.admin.auth)
    ).json()

    entry = audit["items"][0]
    assert entry["before"]["user_monthly_usd"] is None
    assert entry["after"]["user_monthly_usd"] == "5"
    assert entry["after"]["provider_monthly_usd"] == {"gemini": "50"}


# ------------------------------------------------------------------ bases por persona (M4)
DB_1 = "7a1f3c52-9d4e-4b6a-8c0d-1e2f3a4b5c6d"
DB_2 = "11111111-2222-4333-8444-555555555555"
ACCESS_BODY: dict[str, Any] = {
    "default_databases": [DB_1],
    "user_databases": {USER_A: [DB_1, DB_2], USER_B: []},
}


async def test_access_policy_is_empty_by_default_and_not_sent(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    body = (await heartbeat(fx, linked)).json()

    assert body["policy"]["access"] is None
    client = (await fx.console.http.get(f"{API}/clients/{client_id}", headers=fx.admin.auth)).json()
    assert client["access_policy"] == {
        "default_databases": None,
        "user_databases": {},
        "groups": [],
    }


async def test_access_policy_travels_in_the_heartbeat_and_matches_the_contract(
    fx: Fixture,
) -> None:
    from tests.test_api import assert_matches_schema

    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    res = await fx.console.http.put(
        f"{API}/clients/{client_id}/access-policy", json=ACCESS_BODY, headers=fx.admin.auth
    )

    assert res.status_code == 200, res.text
    beat = (await heartbeat(fx, linked)).json()
    assert beat["policy"]["access"] == {
        "default_databases": [DB_1],
        "user_databases": {USER_A: [DB_1, DB_2], USER_B: []},
    }
    assert_matches_schema("heartbeat.response", beat)


async def test_an_empty_user_list_is_kept_it_means_no_databases(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)
    await fx.console.http.put(
        f"{API}/clients/{client_id}/access-policy",
        json={"user_databases": {USER_B: []}},
        headers=fx.admin.auth,
    )

    access = (await heartbeat(fx, linked)).json()["policy"]["access"]

    assert access == {"default_databases": None, "user_databases": {USER_B: []}}


async def test_access_policy_can_be_cleared(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)
    await fx.console.http.put(
        f"{API}/clients/{client_id}/access-policy", json=ACCESS_BODY, headers=fx.admin.auth
    )

    await fx.console.http.put(
        f"{API}/clients/{client_id}/access-policy", json={}, headers=fx.admin.auth
    )

    assert (await heartbeat(fx, linked)).json()["policy"]["access"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"default_databases": ["no-es-un-uuid"]},
        {"user_databases": {"no-es-un-user-ref": [DB_1]}},
        {"user_databases": {USER_A: ["no-es-un-uuid"]}},
        {"default_databases": [DB_1], "campo_extra": 1},
    ],
)
async def test_invalid_access_policy_is_rejected(fx: Fixture, body: dict[str, Any]) -> None:
    client_id = await make_client(fx)

    res = await fx.console.http.put(
        f"{API}/clients/{client_id}/access-policy", json=body, headers=fx.admin.auth
    )

    assert res.status_code == 422, res.text


async def test_only_admin_can_change_the_access_policy(fx: Fixture) -> None:
    client_id = await make_client(fx)
    for who in (fx.soporte, fx.comercial):
        res = await fx.console.http.put(
            f"{API}/clients/{client_id}/access-policy", json=ACCESS_BODY, headers=who.auth
        )
        assert res.status_code == 403


async def test_access_policy_changes_are_audited(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await fx.console.http.put(
        f"{API}/clients/{client_id}/access-policy", json=ACCESS_BODY, headers=fx.admin.auth
    )

    audit = (
        await fx.console.http.get(f"{API}/audit?action=client.access_policy", headers=fx.admin.auth)
    ).json()

    entry = audit["items"][0]
    assert entry["before"]["default_databases"] is None
    assert entry["after"]["default_databases"] == [DB_1]


# ------------------------------------------------------------------ grupos (compilan a reglas)
USER_C = "c" * 32


def _group(name: str, members: list[str], databases: list[str]) -> dict[str, Any]:
    return {"name": name, "members": members, "databases": databases}


async def _put_access(fx: Fixture, client_id: str, body: dict[str, Any]) -> Any:
    return await fx.console.http.put(
        f"{API}/clients/{client_id}/access-policy", json=body, headers=fx.admin.auth
    )


async def test_a_group_is_compiled_into_per_person_rules(fx: Fixture) -> None:
    from tests.test_api import assert_matches_schema

    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    res = await _put_access(
        fx, client_id, {"groups": [_group("Soporte norte", [USER_A, USER_B], [DB_1])]}
    )

    assert res.status_code == 200, res.text
    beat = (await heartbeat(fx, linked)).json()
    assert beat["policy"]["access"] == {
        "default_databases": None,
        "user_databases": {USER_A: [DB_1], USER_B: [DB_1]},
    }
    assert_matches_schema("heartbeat.response", beat)


async def test_a_person_in_two_groups_gets_the_union(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    await _put_access(
        fx,
        client_id,
        {
            "groups": [
                _group("Norte", [USER_A], [DB_1]),
                _group("Sur", [USER_A, USER_B], [DB_2]),
            ]
        },
    )

    rules = (await heartbeat(fx, linked)).json()["policy"]["access"]["user_databases"]
    assert sorted(rules[USER_A]) == sorted([DB_1, DB_2])
    assert rules[USER_B] == [DB_2]


async def test_a_personal_rule_wins_over_the_groups(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    await _put_access(
        fx,
        client_id,
        {
            "groups": [_group("Norte", [USER_A, USER_B], [DB_1])],
            "user_databases": {USER_A: [DB_2]},
        },
    )

    rules = (await heartbeat(fx, linked)).json()["policy"]["access"]["user_databases"]
    assert rules[USER_A] == [DB_2]
    assert rules[USER_B] == [DB_1]


async def test_a_group_without_databases_leaves_its_members_without_any(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    await _put_access(fx, client_id, {"groups": [_group("Sin bases", [USER_A], [])]})

    rules = (await heartbeat(fx, linked)).json()["policy"]["access"]["user_databases"]
    assert rules == {USER_A: []}


async def test_groups_keep_their_id_and_members_in_the_console(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await _put_access(fx, client_id, {"groups": [_group("Norte", [USER_A], [DB_1])]})

    got = await fx.console.http.get(f"{API}/clients/{client_id}", headers=fx.admin.auth)
    group = got.json()["access_policy"]["groups"][0]
    assert group["name"] == "Norte"
    assert group["members"] == [USER_A]
    assert len(group["id"]) == 32

    # Al reenviar con el id, se conserva.
    await _put_access(
        fx,
        client_id,
        {"groups": [{**_group("Norte", [USER_A, USER_C], [DB_1]), "id": group["id"]}]},
    )
    again = await fx.console.http.get(f"{API}/clients/{client_id}", headers=fx.admin.auth)
    saved = again.json()["access_policy"]["groups"][0]
    assert saved["id"] == group["id"]
    assert saved["members"] == [USER_A, USER_C]


@pytest.mark.parametrize(
    "groups",
    [
        [_group("", [USER_A], [DB_1])],
        [_group("Norte", ["no-es-un-user-ref"], [DB_1])],
        [_group("Norte", [USER_A], ["no-es-un-uuid"])],
        [_group("Norte", [USER_A], [DB_1]), _group("norte", [USER_B], [DB_2])],
    ],
)
async def test_invalid_groups_are_rejected(fx: Fixture, groups: list[dict[str, Any]]) -> None:
    client_id = await make_client(fx)

    res = await _put_access(fx, client_id, {"groups": groups})

    assert res.status_code == 422, res.text


async def test_groups_are_audited(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await _put_access(fx, client_id, {"groups": [_group("Norte", [USER_A], [DB_1])]})

    audit = (
        await fx.console.http.get(f"{API}/audit?action=client.access_policy", headers=fx.admin.auth)
    ).json()

    assert audit["items"][0]["after"]["groups"][0]["name"] == "Norte"


# ------------------------------------------------------------------ topes de IA por grupo
def _capped(name: str, members: list[str], cap: str | None) -> dict[str, Any]:
    return {"name": name, "members": members, "databases": [DB_1], "user_monthly_usd": cap}


async def _put_ai(fx: Fixture, client_id: str, body: dict[str, Any]) -> Any:
    return await fx.console.http.put(
        f"{API}/clients/{client_id}/ai-policy", json=body, headers=fx.admin.auth
    )


async def test_a_group_cap_travels_as_a_personal_cap_of_its_members(fx: Fixture) -> None:
    from tests.test_api import assert_matches_schema

    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    await _put_access(fx, client_id, {"groups": [_capped("Soporte", [USER_A, USER_B], "7.5")]})

    beat = (await heartbeat(fx, linked)).json()
    assert beat["policy"]["ai"]["user_overrides"] == {USER_A: "7.5", USER_B: "7.5"}
    assert_matches_schema("heartbeat.response", beat)


async def test_the_highest_group_cap_wins_for_a_person_in_two_groups(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    await _put_access(
        fx,
        client_id,
        {
            "groups": [
                _capped("Chico", [USER_A, USER_B], "5"),
                _capped("Grande", [USER_A], "20"),
            ]
        },
    )

    caps = (await heartbeat(fx, linked)).json()["policy"]["ai"]["user_overrides"]
    assert caps == {USER_A: "20", USER_B: "5"}


async def test_a_personal_cap_wins_over_the_group_cap(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    await _put_access(fx, client_id, {"groups": [_capped("Soporte", [USER_A, USER_B], "5")]})
    await _put_ai(fx, client_id, {"user_overrides": {USER_A: "1"}})

    ai = (await heartbeat(fx, linked)).json()["policy"]["ai"]
    assert ai["user_overrides"] == {USER_A: "1", USER_B: "5"}


async def test_group_caps_keep_the_rest_of_the_ai_policy(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    await _put_ai(fx, client_id, {"user_monthly_usd": "3", "allowed_providers": ["claude"]})
    await _put_access(fx, client_id, {"groups": [_capped("Soporte", [USER_A], "9")]})

    ai = (await heartbeat(fx, linked)).json()["policy"]["ai"]
    assert ai["user_monthly_usd"] == "3"
    assert ai["allowed_providers"] == ["claude"]
    assert ai["user_overrides"] == {USER_A: "9"}


async def test_a_group_without_cap_adds_nothing(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)

    await _put_access(fx, client_id, {"groups": [_capped("Sin tope", [USER_A], None)]})

    assert (await heartbeat(fx, linked)).json()["policy"]["ai"] is None


async def test_the_group_cap_is_stored_and_audited(fx: Fixture) -> None:
    client_id = await make_client(fx)
    await _put_access(fx, client_id, {"groups": [_capped("Soporte", [USER_A], "7.5")]})

    got = await fx.console.http.get(f"{API}/clients/{client_id}", headers=fx.admin.auth)
    assert got.json()["access_policy"]["groups"][0]["user_monthly_usd"] == "7.5"
    audit = (
        await fx.console.http.get(f"{API}/audit?action=client.access_policy", headers=fx.admin.auth)
    ).json()
    assert audit["items"][0]["after"]["groups"][0]["user_monthly_usd"] == "7.5"


async def test_an_invalid_group_cap_is_rejected(fx: Fixture) -> None:
    client_id = await make_client(fx)

    res = await _put_access(fx, client_id, {"groups": [_capped("Soporte", [USER_A], "-3")]})

    assert res.status_code == 422, res.text


async def test_group_and_personal_caps_cannot_exceed_the_contract_limit(fx: Fixture) -> None:
    client_id = await make_client(fx)
    members = [f"{i:032x}" for i in range(1, 501)]
    ok = await _put_access(fx, client_id, {"groups": [_capped("Todos", members, "5")]})
    assert ok.status_code == 200, ok.text

    # Una persona más con tope propio: 501 excepciones compiladas.
    res = await _put_ai(fx, client_id, {"user_overrides": {"f" * 32: "1"}})

    assert res.status_code == 422, res.text
