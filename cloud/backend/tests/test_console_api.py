"""API de la consola (§3, §8.1): permisos por rol, acciones y auditoría."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.modules.audit.domain import RequestContext
from app.modules.console.application import StaffActions
from app.modules.console.queries import is_outdated, version_key
from app.modules.staff.application import AuthDeps
from app.modules.staff.domain import LastAdminProtected, Role
from app.modules.staff.infrastructure import SqlAlchemySessionRepository, SqlAlchemyStaffRepository
from tests.console_helpers import ConsoleEnv, Session

API = "/console/api"
REDEEM = "/api/v1/enrollments/redeem"
HEARTBEAT = "/api/v1/instances/heartbeat"
ROTATE = "/api/v1/instances/credentials/rotate"


@dataclass
class Fixture:
    console: ConsoleEnv
    admin: Session
    soporte: Session
    comercial: Session


@pytest.fixture
async def fx(console: ConsoleEnv) -> Fixture:
    admin = await console.onboard("admin@seo.example", Role.ADMIN)
    soporte = await console.onboard("soporte@seo.example", Role.SOPORTE)
    comercial = await console.onboard("comercial@seo.example", Role.COMERCIAL)
    return Fixture(console, admin, soporte, comercial)


async def make_client(fx: Fixture, code: str = "FARMX", name: str = "Farmacias X") -> str:
    res = await fx.console.http.post(
        f"{API}/clients", json={"code": code, "name": name}, headers=fx.admin.auth
    )
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


@dataclass
class Linked:
    instance_id: str
    secret: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.secret}"}


async def link_instance(fx: Fixture, client_id: str, *, fingerprint: str = "fp-1") -> Linked:
    created = await fx.console.http.post(
        f"{API}/clients/{client_id}/enrollment-tokens", json={}, headers=fx.soporte.auth
    )
    assert created.status_code == 201, created.text
    res = await fx.console.http.post(
        REDEEM,
        json={
            "token": created.json()["token"],
            "instance": {
                "name": "SRV-FARMX",
                "deployment_mode": "server",
                "version": "v1.1.0",
                "commit": "abc1234",
                "os": "Windows Server 2022",
                "agent_db_engine": "postgresql",
                "fingerprint": fingerprint,
            },
        },
    )
    assert res.status_code == 201, res.text
    return Linked(res.json()["instance_id"], res.json()["instance_secret"])


async def heartbeat(fx: Fixture, who: Linked, fingerprint: str = "fp-1") -> httpx.Response:
    return await fx.console.http.post(
        HEARTBEAT,
        json={
            "sent_at": fx.console.clock.now.isoformat(),
            "fingerprint": fingerprint,
            "version": "v1.1.0",
            "deployment_mode": "server",
        },
        headers=who.auth,
    )


# ------------------------------------------------------------------ permisos por rol


async def test_permission_matrix_over_http(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)
    iid = linked.instance_id

    # (método, ruta, cuerpo, roles que SÍ pueden)
    admin, soporte, comercial = "admin", "soporte", "comercial"
    cases: list[tuple[str, str, dict[str, Any] | None, set[str]]] = [
        ("GET", "/clients", None, {admin, soporte, comercial}),
        ("GET", f"/clients/{client_id}", None, {admin, soporte, comercial}),
        ("POST", "/clients", {"code": "NUEVO1", "name": "Nuevo"}, {admin, comercial}),
        ("PATCH", f"/clients/{client_id}", {"name": "Otro"}, {admin, comercial}),
        ("GET", "/instances", None, {admin, soporte, comercial}),
        ("GET", f"/instances/{iid}", None, {admin, soporte, comercial}),
        ("GET", f"/instances/{iid}/heartbeats", None, {admin, soporte}),
        ("POST", f"/instances/{iid}/request-rotation", None, {admin, soporte}),
        ("GET", f"/clients/{client_id}/enrollment-tokens", None, {admin, soporte}),
        ("POST", f"/clients/{client_id}/enrollment-tokens", {}, {admin, soporte}),
        ("GET", "/staff", None, {admin}),
        ("GET", "/audit", None, {admin}),
        ("POST", f"/clients/{client_id}/suspend", None, {admin}),
        ("POST", f"/clients/{client_id}/activate", None, {admin}),
    ]
    sessions = {admin: fx.admin, soporte: fx.soporte, comercial: fx.comercial}
    for method, path, body, allowed in cases:
        for role, session in sessions.items():
            payload = body
            if method == "POST" and path == "/clients":
                # Un código distinto por rol: el alta no debe chocar con la del rol anterior.
                payload = {"code": f"X{role[:4].upper()}", "name": "Nuevo"}
            res = await fx.console.http.request(
                method, f"{API}{path}", json=payload, headers=session.auth
            )
            if role in allowed:
                assert res.status_code < 400, (method, path, role, res.text)
            else:
                assert res.status_code == 403, (method, path, role, res.status_code)
                assert res.json()["errorCode"] == "forbidden"


async def test_technical_fields_only_for_technical_roles(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)
    assert (await heartbeat(fx, linked)).status_code == 200
    path = f"{API}/instances/{linked.instance_id}"

    technical = (await fx.console.http.get(path, headers=fx.soporte.auth)).json()
    assert technical["fingerprint"] == "fp-1"
    assert technical["last_heartbeat"]["version"] == "v1.1.0"

    basic = (await fx.console.http.get(path, headers=fx.comercial.auth)).json()
    assert basic["fingerprint"] is None
    assert basic["last_heartbeat"] is None
    assert basic["clock_skew_seconds"] is None
    assert basic["online"] is True


# ------------------------------------------------------------------ clientes


async def test_client_lifecycle_and_listing(fx: Fixture) -> None:
    a = await make_client(fx, "FARMA", "Farmacia Alfa")
    await make_client(fx, "AGRO1", "Agro Beta")
    await link_instance(fx, a)

    page = (await fx.console.http.get(f"{API}/clients", headers=fx.comercial.auth)).json()
    assert page["total"] == 2
    assert [c["code"] for c in page["items"]] == ["AGRO1", "FARMA"]
    farma = next(c for c in page["items"] if c["code"] == "FARMA")
    assert farma["instances_total"] == 1

    found = (await fx.console.http.get(f"{API}/clients?q=alfa", headers=fx.comercial.auth)).json()
    assert [c["code"] for c in found["items"]] == ["FARMA"]

    limited = (
        await fx.console.http.get(f"{API}/clients?limit=1&offset=1", headers=fx.comercial.auth)
    ).json()
    assert limited["total"] == 2
    assert [c["code"] for c in limited["items"]] == ["FARMA"]

    patched = await fx.console.http.patch(
        f"{API}/clients/{a}",
        json={"name": "  Farmacia Alfa SAS ", "nit": "900123"},
        headers=fx.comercial.auth,
    )
    assert patched.json()["name"] == "Farmacia Alfa SAS"
    assert patched.json()["nit"] == "900123"


async def test_duplicate_client_code_and_invalid_code(fx: Fixture) -> None:
    await make_client(fx)
    dup = await fx.console.http.post(
        f"{API}/clients", json={"code": "FARMX", "name": "Otra"}, headers=fx.admin.auth
    )
    assert dup.status_code == 400
    assert dup.json()["errorCode"] == "client_code_already_exists"
    bad = await fx.console.http.post(
        f"{API}/clients", json={"code": "minus", "name": "Otra"}, headers=fx.admin.auth
    )
    assert bad.json()["errorCode"] == "invalid_client_code"


async def test_suspending_a_client_suspends_only_its_active_instances(fx: Fixture) -> None:
    client_id = await make_client(fx)
    first = await link_instance(fx, client_id)
    second = await link_instance(fx, client_id, fingerprint="fp-2")
    # Una instancia ya suspendida a mano antes: no debe reactivarse con el cliente.
    manual = await fx.console.http.post(
        f"{API}/instances/{second.instance_id}/suspend", headers=fx.soporte.auth
    )
    assert manual.json()["status_reason"] == "manual"

    res = await fx.console.http.post(f"{API}/clients/{client_id}/suspend", headers=fx.admin.auth)
    assert res.json()["status"] == "suspended"
    hb = await heartbeat(fx, first)
    assert hb.json()["instance_status"] == "suspended"

    # Con el cliente suspendido no se emiten tokens nuevos.
    blocked = await fx.console.http.post(
        f"{API}/clients/{client_id}/enrollment-tokens", json={}, headers=fx.soporte.auth
    )
    assert blocked.status_code == 403
    assert blocked.json()["errorCode"] == "client_suspended"

    await fx.console.http.post(f"{API}/clients/{client_id}/activate", headers=fx.admin.auth)
    assert (await heartbeat(fx, first)).json()["instance_status"] == "active"
    still = await fx.console.http.get(
        f"{API}/instances/{second.instance_id}", headers=fx.soporte.auth
    )
    assert still.json()["status"] == "suspended"
    assert still.json()["status_reason"] == "manual"


# ------------------------------------------------------------------ instancias


async def test_revoke_requires_typed_confirmation(fx: Fixture) -> None:
    linked = await link_instance(fx, await make_client(fx))
    path = f"{API}/instances/{linked.instance_id}/revoke"
    wrong = await fx.console.http.post(path, json={"confirm": "revocar"}, headers=fx.soporte.auth)
    assert wrong.status_code == 422
    assert wrong.json()["errorCode"] == "confirmation_required"
    ok = await fx.console.http.post(path, json={"confirm": "REVOCAR"}, headers=fx.soporte.auth)
    assert ok.json()["status"] == "revoked"
    # Irreversible: activar de nuevo falla y el secreto queda inutilizable.
    again = await fx.console.http.post(
        f"{API}/instances/{linked.instance_id}/activate", headers=fx.soporte.auth
    )
    assert again.status_code == 409  # conflicto de estado, no "sesión vencida"
    assert again.json()["errorCode"] == "instance_revoked"
    assert (await heartbeat(fx, linked)).status_code == 401


async def test_fingerprint_mismatch_is_confirmed_from_the_console(fx: Fixture) -> None:
    linked = await link_instance(fx, await make_client(fx))
    clone = await heartbeat(fx, linked, fingerprint="otra-maquina")
    assert clone.json()["instance_status"] == "suspended"
    assert clone.json()["notices"][0]["code"] == "fingerprint_mismatch"

    detail = (
        await fx.console.http.get(f"{API}/instances/{linked.instance_id}", headers=fx.soporte.auth)
    ).json()
    assert detail["status_reason"] == "fingerprint_mismatch"

    confirmed = await fx.console.http.post(
        f"{API}/instances/{linked.instance_id}/confirm-fingerprint", headers=fx.soporte.auth
    )
    assert confirmed.json()["status"] == "active"
    assert confirmed.json()["fingerprint"] == "otra-maquina"
    assert (await heartbeat(fx, linked, fingerprint="otra-maquina")).json()[
        "instance_status"
    ] == "active"


async def test_rotation_request_travels_in_heartbeat_until_rotated(fx: Fixture) -> None:
    linked = await link_instance(fx, await make_client(fx))
    before = await heartbeat(fx, linked)
    assert before.json()["notices"] == []

    await fx.console.http.post(
        f"{API}/instances/{linked.instance_id}/request-rotation", headers=fx.soporte.auth
    )
    notified = await heartbeat(fx, linked)
    assert [n["code"] for n in notified.json()["notices"]] == ["rotate_credentials"]
    # Sigue avisando hasta que la instancia rote.
    assert [n["code"] for n in (await heartbeat(fx, linked)).json()["notices"]] == [
        "rotate_credentials"
    ]

    rotated = await fx.console.http.post(ROTATE, headers=linked.auth)
    assert rotated.status_code == 200
    new = Linked(linked.instance_id, rotated.json()["instance_secret"])
    assert (await heartbeat(fx, new)).json()["notices"] == []


async def test_instance_filters_and_heartbeat_pagination(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)
    for _ in range(3):
        fx.console.clock.advance(minutes=3)
        assert (await heartbeat(fx, linked)).status_code == 200

    online = await fx.console.http.get(
        f"{API}/instances?connectivity=online&client_id={client_id}", headers=fx.soporte.auth
    )
    assert len(online.json()) == 1
    fx.console.clock.advance(minutes=20)
    fresh = await fx.console.login("soporte@seo.example")  # el access token dura 15 min
    offline = await fx.console.http.get(f"{API}/instances?connectivity=offline", headers=fresh.auth)
    assert [i["id"] for i in offline.json()] == [linked.instance_id]

    first = await fx.console.http.get(
        f"{API}/instances/{linked.instance_id}/heartbeats?limit=2", headers=fresh.auth
    )
    body = first.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"]
    second = await fx.console.http.get(
        f"{API}/instances/{linked.instance_id}/heartbeats?limit=2&cursor={body['next_cursor']}",
        headers=fresh.auth,
    )
    ids = {h["id"] for h in body["items"]} | {h["id"] for h in second.json()["items"]}
    assert len(ids) == 3  # 3 heartbeats, sin repetidos ni saltos
    assert second.json()["next_cursor"] is None


def test_version_helpers() -> None:
    assert version_key("v1.2.3") == (1, 2, 3)
    assert version_key("v1.2.0-34-g70e94ae") == (1, 2, 0)
    assert version_key("dev") is None
    assert is_outdated("v1.1.0", "v1.2.0")
    assert not is_outdated("v1.2.0", "v1.2.0")
    assert not is_outdated("dev", "v1.2.0")
    assert not is_outdated("v1.0.0", None)


# ------------------------------------------------------------------ tokens


async def test_token_plaintext_is_shown_only_on_creation(fx: Fixture) -> None:
    client_id = await make_client(fx)
    created = await fx.console.http.post(
        f"{API}/clients/{client_id}/enrollment-tokens",
        json={"expires_hours": 24},
        headers=fx.soporte.auth,
    )
    plaintext = created.json()["token"]
    assert plaintext.startswith("svk_enr_")

    listing = await fx.console.http.get(
        f"{API}/clients/{client_id}/enrollment-tokens", headers=fx.soporte.auth
    )
    assert plaintext not in listing.text
    assert "token_hash" not in listing.text
    assert listing.json()[0]["state"] == "pending"
    assert listing.json()[0]["created_by"] == "soporte@seo.example"

    revoked = await fx.console.http.delete(
        f"{API}/enrollment-tokens/{created.json()['id']}", headers=fx.soporte.auth
    )
    assert revoked.status_code == 204
    after = await fx.console.http.get(
        f"{API}/clients/{client_id}/enrollment-tokens", headers=fx.soporte.auth
    )
    assert after.json()[0]["state"] == "revoked"
    # Un token revocado ya no vincula.
    res = await fx.console.http.post(
        REDEEM,
        json={
            "token": plaintext,
            "instance": {
                "name": "X",
                "deployment_mode": "server",
                "os": "Linux",
                "agent_db_engine": "postgresql",
                "fingerprint": "f",
            },
        },
    )
    assert res.status_code == 404


async def test_token_expiration_is_bounded(fx: Fixture) -> None:
    client_id = await make_client(fx)
    res = await fx.console.http.post(
        f"{API}/clients/{client_id}/enrollment-tokens",
        json={"expires_hours": 500},
        headers=fx.soporte.auth,
    )
    assert res.status_code == 422


# ------------------------------------------------------------------ staff


async def test_staff_management(fx: Fixture) -> None:
    created = await fx.console.http.post(
        f"{API}/staff",
        json={"email": "Nuevo@Seo.example", "full_name": "Nueva Persona", "role": "soporte"},
        headers=fx.admin.auth,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == "nuevo@seo.example"
    assert len(body["temporary_password"]) >= 12
    assert body["mfa_enabled"] is False

    listing = await fx.console.http.get(f"{API}/staff", headers=fx.admin.auth)
    assert "temporary_password" not in listing.text
    assert "password_hash" not in listing.text

    dup = await fx.console.http.post(
        f"{API}/staff",
        json={"email": "nuevo@seo.example", "full_name": "X", "role": "admin"},
        headers=fx.admin.auth,
    )
    assert dup.status_code == 409

    patched = await fx.console.http.patch(
        f"{API}/staff/{body['id']}", json={"role": "comercial"}, headers=fx.admin.auth
    )
    assert patched.json()["role"] == "comercial"


async def test_admin_cannot_deactivate_or_demote_self(fx: Fixture) -> None:
    me = (await fx.console.http.get(f"{API}/me", headers=fx.admin.auth)).json()
    deactivate = await fx.console.http.post(
        f"{API}/staff/{me['id']}/deactivate", headers=fx.admin.auth
    )
    assert deactivate.status_code == 422
    demote = await fx.console.http.patch(
        f"{API}/staff/{me['id']}", json={"role": "soporte"}, headers=fx.admin.auth
    )
    assert demote.status_code == 422


async def test_last_active_admin_is_protected(fx: Fixture) -> None:
    """Otro actor intenta desactivar/degradar al único admin: se rechaza."""
    me = (await fx.console.http.get(f"{API}/me", headers=fx.admin.auth)).json()
    async with fx.console.maker() as s, s.begin():
        from app.modules.audit.application import AuditRecorder
        from app.modules.audit.infrastructure import SqlAlchemyAuditRepository

        deps = AuthDeps(
            users=SqlAlchemyStaffRepository(s),
            sessions=SqlAlchemySessionRepository(s),
            audit=AuditRecorder(SqlAlchemyAuditRepository(s), fx.console.clock),
            security=fx.console.app.state.staff_security,
            clock=fx.console.clock,
        )
        actions = StaffActions(deps)
        outsider = RequestContext(actor_staff_id=uuid4(), actor_email="otro@seo.example")
        from uuid import UUID

        with pytest.raises(LastAdminProtected):
            await actions.deactivate(UUID(me["id"]), outsider)
        with pytest.raises(LastAdminProtected):
            await actions.update(UUID(me["id"]), full_name=None, role=Role.SOPORTE, ctx=outsider)


async def test_deactivated_user_loses_access_and_reset_mfa_revokes_sessions(fx: Fixture) -> None:
    target = (await fx.console.http.get(f"{API}/me", headers=fx.soporte.auth)).json()
    assert (await fx.console.http.get(f"{API}/clients", headers=fx.soporte.auth)).status_code == 200

    reset = await fx.console.http.post(
        f"{API}/staff/{target['id']}/reset-mfa", headers=fx.admin.auth
    )
    assert reset.json()["mfa_enabled"] is False
    assert (await fx.console.http.get(f"{API}/clients", headers=fx.soporte.auth)).status_code == 401

    # Sin TOTP, su próximo ingreso vuelve a pedir la configuración.
    login = await fx.console.http.post(
        "/console/auth/login",
        json={"email": "soporte@seo.example", "password": fx.soporte.password},
    )
    assert login.json()["status"] == "mfa_setup_required"

    off = await fx.console.http.post(
        f"{API}/staff/{target['id']}/deactivate", headers=fx.admin.auth
    )
    assert off.json()["is_active"] is False
    blocked = await fx.console.http.post(
        "/console/auth/login",
        json={"email": "soporte@seo.example", "password": fx.soporte.password},
    )
    assert blocked.status_code == 401


# ------------------------------------------------------------------ auditoría


async def test_every_write_is_audited_with_actor_and_no_secrets(fx: Fixture) -> None:
    client_id = await make_client(fx)
    linked = await link_instance(fx, client_id)
    await fx.console.http.post(
        f"{API}/instances/{linked.instance_id}/suspend", headers=fx.soporte.auth
    )
    await fx.console.http.post(f"{API}/clients/{client_id}/suspend", headers=fx.admin.auth)

    res = await fx.console.http.get(f"{API}/audit?limit=200", headers=fx.admin.auth)
    entries = res.json()["items"]
    actions = {e["action"] for e in entries}
    assert {"client.create", "token.create", "instance.suspend", "client.suspend"} <= actions

    suspend = next(e for e in entries if e["action"] == "instance.suspend")
    assert suspend["actor_email"] == "soporte@seo.example"
    assert suspend["before"]["status"] == "active"
    assert suspend["after"]["status"] == "suspended"
    assert suspend["target_id"] == linked.instance_id

    dump = await fx.console.audit_rows_text()
    assert "svk_enr_" not in dump
    assert "svk_ins_" not in dump


async def test_audit_filters_and_pagination(fx: Fixture) -> None:
    await make_client(fx, "AAA1", "Uno")
    await make_client(fx, "BBB2", "Dos")
    only = await fx.console.http.get(f"{API}/audit?action=client.create", headers=fx.admin.auth)
    assert {e["action"] for e in only.json()["items"]} == {"client.create"}
    assert len(only.json()["items"]) == 2

    page1 = (await fx.console.http.get(f"{API}/audit?limit=2", headers=fx.admin.auth)).json()
    assert len(page1["items"]) == 2
    page2 = (
        await fx.console.http.get(
            f"{API}/audit?limit=2&cursor={page1['next_cursor']}", headers=fx.admin.auth
        )
    ).json()
    assert {e["id"] for e in page1["items"]}.isdisjoint({e["id"] for e in page2["items"]})
