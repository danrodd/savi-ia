"""Segundo factor: desafío en el login, configuración, verificación y restablecimiento.

Se prueba el servicio con un repositorio en memoria y el JWT real, y las rutas HTTP con
FastAPI. La contraseña del ERP no interviene: es un paso anterior.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.infrastructure.config import get_settings
from app.modules.auth.application.mfa import MfaChallengeRequired, MfaService
from app.modules.auth.application.use_cases import ResetMfaUseCase
from app.modules.auth.domain.entities import AuthenticatedUser, RefreshTokenRecord, UserTotp
from app.modules.auth.domain.exceptions import (
    InvalidMfaCodeError,
    InvalidTokenError,
    MfaUnavailableError,
)
from app.modules.auth.domain.interfaces import RefreshTokenRepository, TotpRepository
from app.modules.auth.domain.value_objects import TokenPair, TokenPurpose
from app.modules.auth.infrastructure.http import router as auth_router
from app.modules.auth.infrastructure.http.admin import require_platform_admin
from app.modules.auth.infrastructure.http.dependencies import (
    get_login_use_case,
    get_mfa_service,
    get_reset_mfa_use_case,
    get_token_service,
)
from app.modules.auth.infrastructure.http.mfa_admin_routes import router as mfa_admin_router
from app.modules.auth.infrastructure.security import JwtTokenService
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.infrastructure.http.dependencies import get_erp_database_repository
from app.shared.exceptions import register_exception_handlers
from app.shared.rate_limit import get_rate_limiter
from app.shared.security import totp

DB = uuid4()
ADMIN = AuthenticatedUser(
    id=1,
    erp_database_id=DB,
    login="ADMIN",
    full_name="Administrador",
    is_admin=True,
    is_active=True,
)
OPERATOR = AuthenticatedUser(
    id=2, erp_database_id=DB, login="CAJERO", full_name="Cajero", is_admin=False, is_active=True
)
START = datetime(2026, 10, 14, 12, 0, 5, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.value = START

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class MemoryTotpRepository(TotpRepository):
    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, int], UserTotp] = {}
        self.unreadable: set[tuple[UUID, int]] = set()

    async def get(self, *, erp_database_id: UUID, user_id: int) -> UserTotp | None:
        row = self.rows.get((erp_database_id, user_id))
        if row is not None and (erp_database_id, user_id) in self.unreadable:
            return replace(row, secret=None, unreadable=True)
        return row

    async def save_pending(
        self, *, erp_database_id: UUID, user_id: int, user_login: str, secret: str, when: datetime
    ) -> None:
        self.rows[(erp_database_id, user_id)] = UserTotp(
            erp_database_id, user_id, user_login, secret, None, 0
        )

    async def enable(
        self, *, erp_database_id: UUID, user_id: int, last_step: int, when: datetime
    ) -> bool:
        row = self.rows.get((erp_database_id, user_id))
        if row is None or row.enabled:
            return False
        self.rows[(erp_database_id, user_id)] = replace(row, enabled_at=when, last_step=last_step)
        return True

    async def advance_step(self, *, erp_database_id: UUID, user_id: int, step: int) -> bool:
        row = self.rows.get((erp_database_id, user_id))
        if row is None or not row.enabled or row.last_step >= step:
            return False
        self.rows[(erp_database_id, user_id)] = replace(row, last_step=step)
        return True

    async def delete_by_login(self, *, erp_database_id: UUID, user_login: str) -> int | None:
        for key, row in list(self.rows.items()):
            if key[0] == erp_database_id and row.user_login == user_login:
                del self.rows[key]
                return row.user_id
        return None


@dataclass
class Env:
    service: MfaService
    repo: MemoryTotpRepository
    clock: Clock
    tokens: JwtTokenService

    def current_code(self, user: AuthenticatedUser = ADMIN) -> str:
        secret = self.repo.rows[(DB, user.id)].secret
        assert secret is not None
        return totp.code_at(secret, totp.current_step(self.clock()))


def _required_for_admins(user: AuthenticatedUser) -> bool:
    return user.is_admin


@pytest.fixture
def env() -> Iterator[Env]:
    get_settings.cache_clear()
    repo, clock = MemoryTotpRepository(), Clock()
    tokens = JwtTokenService(get_settings())
    service = MfaService(
        totp_repository=repo,
        token_service=tokens,
        is_required=_required_for_admins,
        issuer="SAVI Test",
        now=clock,
    )
    yield Env(service, repo, clock, tokens)
    get_settings.cache_clear()


async def _enroll(env: Env, user: AuthenticatedUser = ADMIN) -> None:
    """Deja a `user` con el segundo factor activo."""
    challenge = await env.service.challenge_for(user)
    assert challenge is not None and challenge.setup_required
    await env.service.begin_setup(challenge.token, account_label="ADMIN@PRUEBA")
    await env.service.confirm_setup(challenge.token, env.current_code(user))


# ── servicio ──────────────────────────────────────────────────────────────────────────────
async def test_policy_decides_who_gets_a_challenge(env: Env) -> None:
    assert await env.service.challenge_for(OPERATOR) is None
    assert await env.service.challenge_for(ADMIN) is not None


async def test_first_login_asks_for_setup_then_for_the_code(env: Env) -> None:
    first = await env.service.challenge_for(ADMIN)
    assert first is not None and first.setup_required

    setup = await env.service.begin_setup(first.token, account_label="ADMIN@PRUEBA")
    assert setup.otpauth_uri.startswith("otpauth://totp/SAVI%20Test%3AADMIN%40PRUEBA")
    user = await env.service.confirm_setup(first.token, env.current_code())
    assert user.login == "ADMIN"

    again = await env.service.challenge_for(ADMIN)
    assert again is not None and not again.setup_required


async def test_wrong_code_does_not_enable_the_factor(env: Env) -> None:
    challenge = await env.service.challenge_for(ADMIN)
    assert challenge is not None
    await env.service.begin_setup(challenge.token, account_label="x")

    with pytest.raises(InvalidMfaCodeError):
        await env.service.confirm_setup(challenge.token, "000000")

    assert not env.repo.rows[(DB, ADMIN.id)].enabled


async def test_verify_accepts_the_next_code_and_rejects_a_replay(env: Env) -> None:
    await _enroll(env)
    env.clock.advance(30)  # el paso con el que se configuró ya está usado
    challenge = await env.service.challenge_for(ADMIN)
    assert challenge is not None
    code = env.current_code()

    assert (await env.service.verify(challenge.token, code)).login == "ADMIN"
    with pytest.raises(InvalidMfaCodeError):
        await env.service.verify(challenge.token, code)


async def test_the_code_used_to_enroll_cannot_log_in(env: Env) -> None:
    await _enroll(env)
    challenge = await env.service.challenge_for(ADMIN)
    assert challenge is not None

    with pytest.raises(InvalidMfaCodeError):
        await env.service.verify(challenge.token, env.current_code())


async def test_an_enabled_factor_cannot_be_reconfigured_with_the_password_alone(
    env: Env,
) -> None:
    """Si bastara la contraseña, robarla sería robar también el segundo factor."""
    await _enroll(env)
    stale_setup = env.tokens.issue_mfa_token(ADMIN, purpose=TokenPurpose.MFA_SETUP, ttl_seconds=600)

    with pytest.raises(MfaUnavailableError):
        await env.service.begin_setup(stale_setup, account_label="x")


async def test_unreadable_secret_blocks_instead_of_degrading_to_setup(env: Env) -> None:
    await _enroll(env)
    env.repo.unreadable.add((DB, ADMIN.id))

    with pytest.raises(MfaUnavailableError):
        await env.service.challenge_for(ADMIN)


async def test_tokens_are_bound_to_their_step(env: Env) -> None:
    setup = env.tokens.issue_mfa_token(ADMIN, purpose=TokenPurpose.MFA_SETUP, ttl_seconds=600)
    verify = env.tokens.issue_mfa_token(ADMIN, purpose=TokenPurpose.MFA, ttl_seconds=300)
    access = env.tokens.issue_access_token(ADMIN)

    with pytest.raises(InvalidTokenError):
        await env.service.verify(setup, "123456")
    with pytest.raises(InvalidTokenError):
        await env.service.begin_setup(verify, account_label="x")
    with pytest.raises(InvalidTokenError):
        await env.service.verify(access, "123456")


async def test_reset_between_login_and_code_forces_a_new_login(env: Env) -> None:
    await _enroll(env)
    env.clock.advance(30)
    challenge = await env.service.challenge_for(ADMIN)
    assert challenge is not None
    del env.repo.rows[(DB, ADMIN.id)]

    with pytest.raises(InvalidTokenError):
        await env.service.verify(challenge.token, "123456")


# ── restablecimiento ──────────────────────────────────────────────────────────────────────
class _Refresh(RefreshTokenRepository):
    def __init__(self) -> None:
        self.revoked: list[tuple[int, UUID]] = []

    async def save(self, record: RefreshTokenRecord) -> None:
        return None

    async def get_by_jti(self, jti: UUID) -> RefreshTokenRecord | None:
        return None

    async def revoke(self, jti: UUID, *, when: datetime) -> bool:
        return False

    async def revoke_all_for_user(
        self, user_id: int, *, erp_database_id: UUID, when: datetime
    ) -> None:
        self.revoked.append((user_id, erp_database_id))


class _Lookup:
    async def database_id_for(self, code: str | None) -> UUID | None:
        return DB if code in (None, "NORTE") else None


async def test_reset_deletes_the_factor_and_closes_sessions(env: Env) -> None:
    await _enroll(env)
    refresh = _Refresh()
    use_case = ResetMfaUseCase(env.repo, refresh, _Lookup())  # type: ignore[arg-type]

    assert await use_case.execute("admin@NORTE")

    assert (DB, ADMIN.id) not in env.repo.rows
    assert refresh.revoked == [(ADMIN.id, DB)]
    # Sin segundo factor no hay nada que restablecer, ni sesiones que cerrar.
    assert not await use_case.execute("ADMIN")
    assert len(refresh.revoked) == 1


async def test_reset_of_an_unknown_client_is_a_no_op(env: Env) -> None:
    use_case = ResetMfaUseCase(env.repo, _Refresh(), _Lookup())  # type: ignore[arg-type]
    assert not await use_case.execute("ADMIN@NOEXISTE")


# ── HTTP ──────────────────────────────────────────────────────────────────────────────────
class _Bases:
    def __init__(self) -> None:
        self._base = ErpDatabase(  # type: ignore[call-arg]
            id=DB, code="PRUEBA", name="Prueba", is_active=True, is_default=True
        )

    async def get_by_id(self, database_id: UUID) -> ErpDatabase | None:
        return self._base if database_id == DB else None


class _FakeLogin:
    """Hace de `LoginUseCase`: acepta una contraseña y delega el desafío al servicio real."""

    def __init__(self, service: MfaService) -> None:
        self._service = service

    async def execute(self, login: str, password: str):  # noqa: ANN201
        from app.modules.auth.domain.exceptions import InvalidCredentialsError

        if password != "correcta":
            raise InvalidCredentialsError
        user = ADMIN if login.upper() == "ADMIN" else OPERATOR
        challenge = await self._service.challenge_for(user)
        if challenge is not None:
            raise MfaChallengeRequired(challenge)
        return TokenPair("access", "refresh", 900), user

    async def issue_session(self, user: AuthenticatedUser):  # noqa: ANN201
        return TokenPair("access", "refresh", 900), user


@pytest.fixture
def client(env: Env) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(mfa_admin_router)
    register_exception_handlers(app)
    app.dependency_overrides[get_mfa_service] = lambda: env.service
    app.dependency_overrides[get_token_service] = lambda: env.tokens
    app.dependency_overrides[get_login_use_case] = lambda: _FakeLogin(env.service)
    app.dependency_overrides[get_erp_database_repository] = lambda: _Bases()
    app.dependency_overrides[require_platform_admin] = lambda: ADMIN
    app.dependency_overrides[get_reset_mfa_use_case] = lambda: ResetMfaUseCase(
        env.repo,
        _Refresh(),
        _Lookup(),  # type: ignore[arg-type]
    )
    get_rate_limiter().reset()
    yield TestClient(app)
    get_rate_limiter().reset()


def _login(client: TestClient, login: str = "ADMIN") -> dict[str, object]:
    response = client.post("/auth/login", json={"login": login, "password": "correcta"})
    assert response.status_code == 200, response.text
    return dict(response.json())


def _enroll_http(client: TestClient, env: Env) -> None:
    challenge = _login(client)
    token = str(challenge["mfa_token"])
    setup = client.post("/auth/mfa/setup", json={"mfa_token": token})
    assert setup.status_code == 200, setup.text
    done = client.post(
        "/auth/mfa/setup/confirm", json={"mfa_token": token, "code": env.current_code()}
    )
    assert done.status_code == 200, done.text


def test_login_of_an_admin_returns_a_challenge_and_no_session(client: TestClient) -> None:
    body = _login(client)

    assert body["status"] == "mfa_setup_required"
    assert "access_token" not in body
    assert "refresh_token" not in body


def test_login_of_a_regular_user_is_unchanged(client: TestClient) -> None:
    body = _login(client, "CAJERO")

    assert body["status"] == "authenticated"
    assert body["access_token"] == "access"


def test_full_flow_setup_then_login_with_code(client: TestClient, env: Env) -> None:
    challenge = _login(client)
    token = str(challenge["mfa_token"])

    setup = client.post("/auth/mfa/setup", json={"mfa_token": token}).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/SAVI%20Test%3AADMIN%40PRUEBA")
    assert len(setup["secret"]) == 32

    confirmed = client.post(
        "/auth/mfa/setup/confirm", json={"mfa_token": token, "code": env.current_code()}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "authenticated"

    env.clock.advance(30)
    second = _login(client)
    assert second["status"] == "mfa_required"
    verified = client.post(
        "/auth/mfa/verify",
        json={"mfa_token": second["mfa_token"], "code": env.current_code()},
    )
    assert verified.status_code == 200
    assert verified.json()["access_token"] == "access"


def test_wrong_code_is_401_with_error_code(client: TestClient, env: Env) -> None:
    _enroll_http(client, env)
    env.clock.advance(30)
    challenge = _login(client)

    response = client.post(
        "/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": "000000"}
    )

    assert response.status_code == 401
    assert response.json()["errorCode"] == "invalid_mfa_code"


def test_a_challenge_token_does_not_open_a_session(client: TestClient) -> None:
    challenge = _login(client)

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {challenge['mfa_token']}"})

    assert response.status_code == 401


def test_code_brute_force_is_blocked_like_the_password(client: TestClient, env: Env) -> None:
    _enroll_http(client, env)
    env.clock.advance(30)
    token = str(_login(client)["mfa_token"])

    for _ in range(5):
        wrong = client.post("/auth/mfa/verify", json={"mfa_token": token, "code": "000000"})
        assert wrong.status_code == 401

    blocked = client.post("/auth/mfa/verify", json={"mfa_token": token, "code": env.current_code()})
    assert blocked.status_code == 429  # ni el código correcto pasa durante el bloqueo


def test_a_correct_password_does_not_reset_the_code_failures(client: TestClient, env: Env) -> None:
    """Si el login correcto limpiara el contador, quien conoce la contraseña intercalaría
    logins con intentos de código y nunca llegaría al bloqueo."""
    _enroll_http(client, env)
    env.clock.advance(30)
    token = str(_login(client)["mfa_token"])
    for _ in range(4):
        client.post("/auth/mfa/verify", json={"mfa_token": token, "code": "000000"})

    token = str(_login(client)["mfa_token"])  # contraseña correcta de nuevo
    client.post("/auth/mfa/verify", json={"mfa_token": token, "code": "000000"})  # 5.º fallo

    blocked = client.post("/auth/mfa/verify", json={"mfa_token": token, "code": "000000"})
    assert blocked.status_code == 429


def test_admin_reset_endpoint(client: TestClient, env: Env) -> None:
    _enroll_http(client, env)

    first = client.post("/admin/mfa/reset", json={"login": "ADMIN@NORTE"})
    second = client.post("/admin/mfa/reset", json={"login": "ADMIN@NORTE"})

    assert first.status_code == 200 and first.json() == {"reset": True}
    assert second.json() == {"reset": False}
    assert (DB, ADMIN.id) not in env.repo.rows
