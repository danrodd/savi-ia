"""Límite de intentos en el login (Fase 2 de seguridad).

Medido antes de esto: 50 logins fallidos lanzados en paralelo se procesaban
todos. Con contraseñas MD5 sin sal en el ERP, la fuerza bruta por la API era
viable. Ver `docs/seguridad/03-fase-2-resistencia.md`.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.exceptions import InvalidCredentialsError
from app.modules.auth.domain.value_objects import TokenPair
from app.modules.auth.infrastructure.http import router as auth_router
from app.modules.auth.infrastructure.http.dependencies import get_login_use_case
from app.shared.exceptions import register_exception_handlers
from app.shared.rate_limit import get_rate_limiter

_GOOD = "correcta"

_USUARIO = AuthenticatedUser(
    id=1,
    erp_database_id=uuid4(),
    login="ADMIN",
    full_name="Administrador",
    is_admin=True,
    is_active=True,
)
_TOKENS = TokenPair(access_token="a", refresh_token="r", access_token_expires_in=900)


class _FakeLoginUseCase:
    """Acepta una sola contraseña. No toca el ERP: lo que se prueba es el
    límite, no la autenticación."""

    def __init__(self) -> None:
        self.intentos = 0

    async def execute(self, login: str, password: str):  # noqa: ANN201
        self.intentos += 1
        if password != _GOOD:
            raise InvalidCredentialsError
        return _TOKENS, _USUARIO


@pytest.fixture
def use_case() -> _FakeLoginUseCase:
    return _FakeLoginUseCase()


@pytest.fixture
def client(use_case: _FakeLoginUseCase) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)
    app.dependency_overrides[get_login_use_case] = lambda: use_case
    get_rate_limiter().reset()
    yield TestClient(app)
    get_rate_limiter().reset()


def _post(client: TestClient, login: str = "ADMIN", password: str = "mala"):  # noqa: ANN202
    return client.post("/auth/login", json={"login": login, "password": password})


def test_wrong_password_is_401_until_the_lockout(
    client: TestClient, use_case: _FakeLoginUseCase
) -> None:
    for _ in range(4):
        assert _post(client).status_code == 401
    assert use_case.intentos == 4


def test_locks_out_after_consecutive_failures(client: TestClient) -> None:
    for _ in range(5):
        _post(client)

    response = _post(client)

    assert response.status_code == 429
    assert response.json()["errorCode"] == "rate_limited"
    assert int(response.headers["Retry-After"]) > 0


def test_lockout_rejects_even_the_right_password(
    client: TestClient, use_case: _FakeLoginUseCase
) -> None:
    """Si la contraseña correcta pasara, el bloqueo no serviría de nada."""
    for _ in range(5):
        _post(client)
    antes = use_case.intentos

    response = _post(client, password=_GOOD)

    assert response.status_code == 429
    # Ni siquiera se llamó al caso de uso: no se paga el viaje al ERP.
    assert use_case.intentos == antes


def test_lockout_is_per_login(client: TestClient) -> None:
    """Bloquear a un usuario no puede dejar afuera a los demás."""
    for _ in range(5):
        _post(client, login="ADMIN")

    assert _post(client, login="OTRO").status_code == 401


def test_login_key_ignores_case(client: TestClient) -> None:
    """Sin normalizar, alternar mayúsculas genera una clave nueva por intento
    y el bloqueo no llega nunca."""
    for login in ("ADMIN", "admin", "Admin", "aDmIn", "ADMIn"):
        _post(client, login=login)

    assert _post(client, login="AdMiN").status_code == 429


def test_successful_logins_do_not_exhaust_the_window(
    client: TestClient, use_case: _FakeLoginUseCase
) -> None:
    """Entrar bien muchas veces no es un ataque.

    La ventana por usuario existe para frenar a quien adivina contraseñas, y
    ese FALLA. Contar también los aciertos dejaba afuera a un usuario legítimo
    que inicia sesión varias veces en un minuto (y rompía los E2E, que es
    donde apareció).
    """
    for _ in range(20):
        assert _post(client, password=_GOOD).status_code == 200

    assert use_case.intentos == 20


def test_rate_limit_can_be_disabled(
    client: TestClient, use_case: _FakeLoginUseCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interruptor para desarrollo y para los E2E."""
    from app.infrastructure.config import get_settings

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()
    try:
        for _ in range(8):
            assert _post(client).status_code == 401
        assert use_case.intentos == 8
    finally:
        get_settings.cache_clear()
