"""Autenticación del staff (§2, §8.1): login, MFA, refresh, bloqueo, permisos y auditoría."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.config import Settings
from app.main import create_app
from app.modules.audit.domain import REDACTED, redact
from app.modules.staff.dependencies import RequirePermission
from app.modules.staff.domain import PERMISSIONS, Permission, Role, WeakPassword, has_permission
from app.modules.staff.security import (
    StaffSecurity,
    otpauth_uri,
    totp_code,
    validate_password_policy,
    verify_totp,
)
from tests.console_helpers import (
    GOOD_PASSWORD,
    LOGIN,
    LOGOUT,
    ME,
    MFA,
    MFA_CONFIRM,
    MFA_SETUP,
    REFRESH,
    ConsoleEnv,
    make_settings,
)
from tests.fakes import FakeClock

# ------------------------------------------------------------------ primitivas


def test_totp_matches_rfc6238_vector() -> None:
    # Secreto ASCII "12345678901234567890" y T=59 s => 94287082 (8 dígitos); 6 => 287082.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp_code(secret, 59 // 30) == "287082"


def test_totp_window_and_single_use() -> None:
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    now = datetime(2026, 1, 1, 12, 0, 10, tzinfo=UTC)
    step = int(now.timestamp() // 30)
    # Ventana ±1.
    for offset in (-1, 0, 1):
        assert verify_totp(secret, totp_code(secret, step + offset), now, 0) == step + offset
    assert verify_totp(secret, totp_code(secret, step + 2), now, 0) is None
    assert verify_totp(secret, totp_code(secret, step - 2), now, 0) is None
    # Un código ya usado (paso <= último aceptado) no vale otra vez.
    assert verify_totp(secret, totp_code(secret, step), now, step) is None
    assert verify_totp(secret, totp_code(secret, step - 1), now, step) is None
    # Formato inválido.
    assert verify_totp(secret, "12ab56", now, 0) is None
    assert verify_totp(secret, "12345", now, 0) is None


def test_otpauth_uri_has_issuer_and_secret() -> None:
    uri = otpauth_uri("ABC234", "ana@seo.example")
    assert uri.startswith("otpauth://totp/SAVI%20Cloud%3Aana%40seo.example?")
    assert "secret=ABC234" in uri
    assert "issuer=SAVI%20Cloud" in uri


@pytest.mark.parametrize(
    "password",
    ["corta", "123456789012", "aaaaaaaaaaaaaaaa", "Password12345", "ana.perez-clave"],
)
def test_weak_passwords_are_rejected(password: str) -> None:
    with pytest.raises(WeakPassword):
        validate_password_policy(password, email="ana.perez@seo.example")


def test_good_password_is_accepted() -> None:
    validate_password_policy(GOOD_PASSWORD, email="ana@seo.example")


async def test_password_hash_is_argon2id_and_verifies() -> None:
    security = StaffSecurity("x" * 40, FakeClock())
    hashed = await security.hash_password("una-clave-de-prueba-larga")
    assert hashed.startswith("$argon2id$")
    assert await security.verify_password(hashed, "una-clave-de-prueba-larga")
    assert not await security.verify_password(hashed, "otra")
    assert not await security.verify_password("no-es-un-hash", "otra")


def test_tokens_are_bound_to_purpose_and_expire() -> None:
    from datetime import timedelta
    from uuid import uuid4

    clock = FakeClock()
    security = StaffSecurity("x" * 40, clock)
    user = uuid4()
    token = security.issue("mfa", user, timedelta(minutes=5))
    assert security.decode(token, "mfa")["sub"] == str(user)
    with pytest.raises(Exception, match="inválido"):
        security.decode(token, "access")
    clock.advance(minutes=6)
    with pytest.raises(Exception, match="venció"):
        security.decode(token, "mfa")
    other = StaffSecurity("y" * 40, clock)
    with pytest.raises(Exception, match="inválido"):
        other.decode(security.issue("mfa", user, timedelta(minutes=5)), "mfa")


def test_redact_hides_secrets_recursively() -> None:
    value = {
        "email": "a@b.c",
        "password": "x",
        "nested": {"enrollment_token": "svk_enr_x", "totp_secret": "S", "ok": 1},
        "items": [{"secret_hash": "h"}, {"fine": True}],
    }
    out = redact(value)
    assert out["email"] == "a@b.c"
    assert out["password"] == REDACTED
    assert out["nested"] == {"enrollment_token": REDACTED, "totp_secret": REDACTED, "ok": 1}
    assert out["items"] == [{"secret_hash": REDACTED}, {"fine": True}]


# ------------------------------------------------------------------ matriz de permisos


def test_permission_matrix_matches_spec() -> None:
    assert set(PERMISSIONS) == set(Permission)
    admin_only = {
        Permission.CLIENTS_SUSPEND,
        Permission.ALERTS_CONFIGURE,
        Permission.STAFF_MANAGE,
        Permission.AUDIT_READ,
    }
    for permission in Permission:
        assert has_permission(Role.ADMIN, permission)
        if permission in admin_only:
            assert not has_permission(Role.SOPORTE, permission)
            assert not has_permission(Role.COMERCIAL, permission)
    assert has_permission(Role.COMERCIAL, Permission.CLIENTS_WRITE)
    assert not has_permission(Role.SOPORTE, Permission.CLIENTS_WRITE)
    assert has_permission(Role.SOPORTE, Permission.TOKENS_MANAGE)
    assert not has_permission(Role.COMERCIAL, Permission.TOKENS_MANAGE)
    assert has_permission(Role.SOPORTE, Permission.INSTANCES_READ_TECHNICAL)
    assert not has_permission(Role.COMERCIAL, Permission.INSTANCES_READ_TECHNICAL)
    assert not has_permission(Role.COMERCIAL, Permission.INSTANCES_MANAGE)


def _api_routes(app: FastAPI) -> list[tuple[APIRoute, str]]:
    """Todas las rutas HTTP con su ruta completa (FastAPI agrupa los routers incluidos)."""
    found: list[tuple[APIRoute, str]] = []
    for route in app.routes:
        original = getattr(route, "original_router", None)
        if original is None:
            if isinstance(route, APIRoute):
                found.append((route, route.path))
            continue
        prefix: str = getattr(route.include_context, "prefix", "")  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportUnknownVariableType,reportAttributeAccessIssue]
        found.extend((r, prefix + r.path) for r in original.routes if isinstance(r, APIRoute))
    return found


async def test_every_console_api_route_requires_a_permission(console: ConsoleEnv) -> None:
    """Falla si aparece una ruta de `/console/api` sin `RequirePermission`."""
    missing: list[str] = []
    seen = 0
    for route, path in _api_routes(console.app):
        if not path.startswith("/console/api"):
            continue
        seen += 1
        calls = [d.call for d in route.dependant.dependencies]
        if not any(isinstance(call, RequirePermission) for call in calls):
            missing.append(f"{sorted(route.methods or [])} {path}")
    assert seen >= 1
    assert missing == []


async def test_console_api_rejects_unauthenticated_requests(console: ConsoleEnv) -> None:
    res = await console.http.get(ME)
    assert res.status_code == 401
    assert res.json()["errorCode"] == "unauthorized"
    bad = await console.http.get(ME, headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


async def test_console_is_disabled_without_secret(sqlite_url: str) -> None:
    app = create_app(Settings(database_url=sqlite_url, env="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        res = await http.post(LOGIN, json={"email": "a@b.co", "password": "x"})
        assert res.status_code == 503
        assert res.json()["errorCode"] == "console_disabled"
    await app.state.engine.dispose()


def test_short_console_secret_is_rejected() -> None:
    with pytest.raises(ValueError, match="CONSOLE_SECRET"):
        Settings(database_url="sqlite+aiosqlite://", console_secret="corto")


# ------------------------------------------------------------------ flujo de acceso


async def test_first_login_requires_mfa_setup_and_new_password(console: ConsoleEnv) -> None:
    temporary = await console.create_staff("ana@seo.example")
    login = await console.http.post(
        LOGIN, json={"email": "ANA@seo.example ", "password": temporary}
    )
    assert login.status_code == 200
    body = login.json()
    assert body["status"] == "mfa_setup_required"
    assert "access_token" not in body  # sin TOTP no hay tokens de acceso
    assert "set-cookie" not in login.headers

    setup = await console.http.post(MFA_SETUP, json={"setup_token": body["token"]})
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")

    # Sin contraseña nueva: no se completa.
    no_password = await console.http.post(
        MFA_CONFIRM, json={"setup_token": body["token"], "code": console.code(secret)}
    )
    assert no_password.status_code == 422
    # Contraseña débil.
    weak = await console.http.post(
        MFA_CONFIRM,
        json={"setup_token": body["token"], "code": console.code(secret), "new_password": "corta"},
    )
    assert weak.status_code == 422
    assert weak.json()["errorCode"] == "weak_password"
    # Código TOTP incorrecto.
    wrong = await console.http.post(
        MFA_CONFIRM,
        json={"setup_token": body["token"], "code": "000000", "new_password": GOOD_PASSWORD},
    )
    assert wrong.status_code == 401
    assert wrong.json()["errorCode"] == "invalid_mfa_code"

    ok = await console.http.post(
        MFA_CONFIRM,
        json={
            "setup_token": body["token"],
            "code": console.code(secret),
            "new_password": GOOD_PASSWORD,
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["must_change_password"] is False
    assert ok.json()["user"]["role"] == "admin"
    assert "savi_console_refresh" in ok.cookies


async def test_setup_cannot_be_skipped_or_repeated(console: ConsoleEnv) -> None:
    await console.onboard("ana@seo.example")
    # La contraseña temporal ya no existe y TOTP ya está activo: el login pide MFA.
    login = await console.http.post(
        LOGIN, json={"email": "ana@seo.example", "password": GOOD_PASSWORD}
    )
    assert login.json()["status"] == "mfa_required"
    # Un token de MFA no sirve para reconfigurar el TOTP.
    again = await console.http.post(MFA_SETUP, json={"setup_token": login.json()["token"]})
    assert again.status_code == 401


async def test_login_mfa_and_me(console: ConsoleEnv) -> None:
    await console.onboard("ana@seo.example", Role.SOPORTE)
    session = await console.login("ana@seo.example")
    me = await console.http.get(ME, headers=session.auth)
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "ana@seo.example"
    assert body["role"] == "soporte"
    assert Permission.TOKENS_MANAGE.value in body["permissions"]
    assert Permission.AUDIT_READ.value not in body["permissions"]


async def test_mfa_code_cannot_be_reused(console: ConsoleEnv) -> None:
    await console.onboard("ana@seo.example")
    console.clock.advance(seconds=31)
    secret = console.secrets_by_email["ana@seo.example"]
    code = console.code(secret)
    first = await console.http.post(
        LOGIN, json={"email": "ana@seo.example", "password": GOOD_PASSWORD}
    )
    ok = await console.http.post(MFA, json={"mfa_token": first.json()["token"], "code": code})
    assert ok.status_code == 200
    second = await console.http.post(
        LOGIN, json={"email": "ana@seo.example", "password": GOOD_PASSWORD}
    )
    replay = await console.http.post(MFA, json={"mfa_token": second.json()["token"], "code": code})
    assert replay.status_code == 401
    assert replay.json()["errorCode"] == "invalid_mfa_code"


async def test_mfa_token_expires_after_five_minutes(console: ConsoleEnv) -> None:
    await console.onboard("ana@seo.example")
    console.clock.advance(seconds=31)
    secret = console.secrets_by_email["ana@seo.example"]
    first = await console.http.post(
        LOGIN, json={"email": "ana@seo.example", "password": GOOD_PASSWORD}
    )
    console.clock.advance(minutes=6)
    res = await console.http.post(
        MFA, json={"mfa_token": first.json()["token"], "code": console.code(secret)}
    )
    assert res.status_code == 401
    assert res.json()["errorCode"] == "invalid_session_token"


async def test_wrong_email_and_wrong_password_look_identical(
    console: ConsoleEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    await console.onboard("ana@seo.example")
    security: StaffSecurity = console.app.state.staff_security
    calls: list[str] = []
    original = security.verify_password

    async def counting(password_hash: str, password: str) -> bool:
        calls.append(password_hash[:9])
        return await original(password_hash, password)

    monkeypatch.setattr(security, "verify_password", counting)

    unknown = await console.http.post(
        LOGIN, json={"email": "nadie@seo.example", "password": "x" * 14}
    )
    wrong = await console.http.post(LOGIN, json={"email": "ana@seo.example", "password": "x" * 14})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
    # Ambos caminos gastaron exactamente una verificación argon2.
    assert len(calls) == 2
    assert all(c == "$argon2id" for c in calls)


async def test_account_locks_after_five_failures_and_unlocks(console: ConsoleEnv) -> None:
    await console.onboard("ana@seo.example")
    for _ in range(5):
        res = await console.http.post(
            LOGIN, json={"email": "ana@seo.example", "password": "incorrecta-1234"}
        )
        assert res.status_code == 401
    # Bloqueada: aun con la contraseña correcta devuelve el mismo error genérico.
    locked = await console.http.post(
        LOGIN, json={"email": "ana@seo.example", "password": GOOD_PASSWORD}
    )
    assert locked.status_code == 401
    assert locked.json()["errorCode"] == "invalid_credentials"
    console.clock.advance(minutes=16)
    ok = await console.http.post(
        LOGIN, json={"email": "ana@seo.example", "password": GOOD_PASSWORD}
    )
    assert ok.status_code == 200
    assert "login_failed" in " ".join(await console.audit_actions())


async def test_wrong_mfa_codes_also_lock(console: ConsoleEnv) -> None:
    await console.onboard("ana@seo.example")
    console.clock.advance(seconds=31)
    first = await console.http.post(
        LOGIN, json={"email": "ana@seo.example", "password": GOOD_PASSWORD}
    )
    token = first.json()["token"]
    for _ in range(5):
        res = await console.http.post(MFA, json={"mfa_token": token, "code": "000000"})
        assert res.status_code == 401
    secret = console.secrets_by_email["ana@seo.example"]
    res = await console.http.post(MFA, json={"mfa_token": token, "code": console.code(secret)})
    assert res.status_code == 401  # bloqueada: ni el código correcto sirve


async def test_login_is_rate_limited_per_ip(console: ConsoleEnv) -> None:
    last: httpx.Response | None = None
    for _ in range(31):
        last = await console.http.post(LOGIN, json={"email": "x@seo.example", "password": "y"})
    assert last is not None
    assert last.status_code == 429
    assert int(last.headers["Retry-After"]) > 0


# ------------------------------------------------------------------ refresh y logout


async def test_cookie_flags_are_http_only_secure_strict(sqlite_url: str) -> None:
    app = create_app(make_settings(sqlite_url, console_cookie_secure=True), clock=FakeClock())
    env = ConsoleEnv(
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test"),
        app,
        app.state.clock,
    )
    temporary = await env.create_staff("ana@seo.example")
    login = await env.http.post(LOGIN, json={"email": "ana@seo.example", "password": temporary})
    token = login.json()["token"]
    secret = (await env.http.post(MFA_SETUP, json={"setup_token": token})).json()["secret"]
    res = await env.http.post(
        MFA_CONFIRM,
        json={"setup_token": token, "code": env.code(secret), "new_password": GOOD_PASSWORD},
    )
    cookie = res.headers["set-cookie"].lower()
    assert "savi_console_refresh=" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
    assert "path=/console/auth" in cookie
    await env.http.aclose()
    await app.state.engine.dispose()


async def test_refresh_rotates_and_detects_reuse(console: ConsoleEnv) -> None:
    await console.onboard("ana@seo.example")
    first_cookie = console.http.cookies.get("savi_console_refresh")
    assert first_cookie

    rotated = await console.http.post(REFRESH)
    assert rotated.status_code == 200, rotated.text
    new_access = rotated.json()["access_token"]
    assert console.http.cookies.get("savi_console_refresh") != first_cookie
    assert (
        await console.http.get(ME, headers={"Authorization": f"Bearer {new_access}"})
    ).status_code == 200

    # Reutilizar el refresh anterior: se rechaza y se revocan TODAS las sesiones.
    console.http.cookies.set("savi_console_refresh", first_cookie, path="/console/auth")
    reuse = await console.http.post(REFRESH)
    assert reuse.status_code == 401
    after = await console.http.get(ME, headers={"Authorization": f"Bearer {new_access}"})
    assert after.status_code == 401
    assert "auth.refresh_reuse_detected" in await console.audit_actions()


async def test_logout_revokes_the_session(console: ConsoleEnv) -> None:
    session = await console.onboard("ana@seo.example")
    out = await console.http.post(LOGOUT)
    assert out.status_code == 204
    assert (await console.http.get(ME, headers=session.auth)).status_code == 401
    assert (await console.http.post(REFRESH)).status_code == 401


async def test_access_token_expires_after_fifteen_minutes(console: ConsoleEnv) -> None:
    session = await console.onboard("ana@seo.example")
    assert (await console.http.get(ME, headers=session.auth)).status_code == 200
    console.clock.advance(minutes=16)
    res = await console.http.get(ME, headers=session.auth)
    assert res.status_code == 401


async def test_refresh_session_has_an_absolute_eight_hour_limit(console: ConsoleEnv) -> None:
    await console.onboard("ana@seo.example")
    console.clock.advance(hours=7)
    assert (await console.http.post(REFRESH)).status_code == 200
    console.clock.advance(hours=2)  # 9 h desde el ingreso, aunque se haya rotado
    assert (await console.http.post(REFRESH)).status_code == 401


# ------------------------------------------------------------------ auditoría


async def test_auth_events_are_audited_without_secrets(console: ConsoleEnv) -> None:
    temporary = await console.create_staff("ana@seo.example")
    session = await console.onboard("bea@seo.example")
    await console.http.post(LOGIN, json={"email": "ana@seo.example", "password": "incorrecta-1234"})
    actions = await console.audit_actions()
    assert "staff.create" in actions
    assert "auth.mfa_enabled" in actions
    assert "auth.login" in actions
    assert "auth.login_failed" in actions
    dump = await console.audit_rows_text()
    for secret in (temporary, GOOD_PASSWORD, session.totp_secret, session.access_token):
        assert secret not in dump


async def test_audit_table_has_no_update_path(console: ConsoleEnv) -> None:
    """El repositorio solo expone `add` y `list`: no hay camino de código para modificar."""
    from app.modules.audit.infrastructure import SqlAlchemyAuditRepository

    public = {n for n in dir(SqlAlchemyAuditRepository) if not n.startswith("_")}
    assert public == {"add", "list"}
