"""`POST /auth/login` con un código de cliente inexistente.

El formulario necesita señalar el código (`USUARIO@CODIGO`) cuando es lo que
está mal, sin dejar de ser un 401 común ni revelar nada sobre el usuario.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.auth.application.use_cases.login import LoginUseCase
from app.modules.auth.domain.exceptions import (
    DatabaseDisabledError,
    DatabaseUnreachableError,
    InvalidCredentialsError,
    UnknownDatabaseError,
)
from app.modules.auth.domain.interfaces import (
    PasswordHasher,
    UserRepository,
    UserRepositoryFactory,
)
from app.modules.auth.domain.interfaces.user_repository import UserWithHash
from app.modules.auth.infrastructure.http import router as auth_router
from app.modules.auth.infrastructure.http.dependencies import get_login_use_case
from app.modules.auth.infrastructure.persistence.erp_user_repository import ErpUserRepository
from app.modules.auth.infrastructure.persistence.erp_user_repository_factory import (
    ErpUserRepositoryFactory,
)
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.infrastructure.http.dependencies import get_erp_database_repository
from app.shared.exceptions import register_exception_handlers
from app.shared.rate_limit import get_rate_limiter


class _BasesFalsas:
    async def get_by_id(self, database_id: UUID) -> ErpDatabase | None:  # noqa: ARG002
        return None


class _FakeLoginUseCase:
    async def execute(self, login: str, password: str):  # noqa: ANN201, ARG002
        if login.endswith("@NOEXISTE"):
            raise UnknownDatabaseError
        if login.endswith("@DESACTIVADA"):
            raise DatabaseDisabledError
        if login.endswith("@SINCONEXION"):
            raise DatabaseUnreachableError
        raise InvalidCredentialsError


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)
    app.dependency_overrides[get_login_use_case] = lambda: _FakeLoginUseCase()
    app.dependency_overrides[get_erp_database_repository] = lambda: _BasesFalsas()
    get_rate_limiter().reset()
    yield TestClient(app)
    get_rate_limiter().reset()


def test_unknown_client_code_has_its_own_error_code(client: TestClient) -> None:
    response = client.post("/auth/login", json={"login": "JPEREZ@NOEXISTE", "password": "x"})

    assert response.status_code == 401
    assert response.json() == {
        "errorCode": "unknown_database",
        "detail": "No encontramos ese cliente. Revisá el código después de la @.",
    }
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_disabled_client_has_its_own_error_code(client: TestClient) -> None:
    response = client.post("/auth/login", json={"login": "JPEREZ@DESACTIVADA", "password": "x"})

    assert response.status_code == 401
    assert response.json() == {
        "errorCode": "database_disabled",
        "detail": "Ese cliente está desactivado en SAVI. Avisale a tu administrador.",
    }
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_unreachable_client_is_a_503_with_its_own_error_code(client: TestClient) -> None:
    response = client.post("/auth/login", json={"login": "JPEREZ@SINCONEXION", "password": "x"})

    assert response.status_code == 503
    assert response.json() == {
        "errorCode": "database_unreachable",
        "detail": (
            "No pudimos conectar con la base de ese cliente. "
            "Probá de nuevo en unos minutos o avisale a tu administrador."
        ),
    }


def test_disabled_client_counts_as_a_failed_attempt_but_unreachable_does_not(
    client: TestClient,
) -> None:
    """Desactivado es un login fallido más; sin conexión no es un intento."""
    for _ in range(5):
        client.post("/auth/login", json={"login": "JPEREZ@SINCONEXION", "password": "x"})
    still_reachable = client.post(
        "/auth/login", json={"login": "JPEREZ@SINCONEXION", "password": "x"}
    )
    assert still_reachable.status_code == 503

    for _ in range(5):
        client.post("/auth/login", json={"login": "JPEREZ@DESACTIVADA", "password": "x"})
    blocked = client.post("/auth/login", json={"login": "JPEREZ@DESACTIVADA", "password": "x"})
    assert blocked.status_code == 429


# ── Caso de uso y repositorio reales (sin HTTP) ──────────────────────


class _RaisingFactory(UserRepositoryFactory):
    def __init__(self, error: Exception | None, repository: UserRepository | None = None) -> None:
        self._error = error
        self._repository = repository

    async def for_code(self, code: str | None) -> UserRepository | None:  # noqa: ARG002
        if self._error is not None:
            raise self._error
        return self._repository

    async def for_database_id(self, database_id: UUID) -> UserRepository | None:  # noqa: ARG002
        return self._repository


class _Hasher(PasswordHasher):
    def __init__(self) -> None:
        self.verified = 0

    def verify(self, plain: str, hashed: str) -> bool:  # noqa: ARG002
        self.verified += 1
        return False

    def hash(self, plain: str) -> str:
        return plain


class _BrokenRepository(UserRepository):
    async def find_by_login(self, login: str) -> UserWithHash | None:  # noqa: ARG002
        raise DatabaseUnreachableError


def _use_case(factory: UserRepositoryFactory, hasher: PasswordHasher) -> LoginUseCase:
    # Solo se ejercitan caminos de fallo: ni el repo de refresh ni el de
    # tokens llegan a usarse.
    return LoginUseCase(factory, None, hasher, None)  # type: ignore[arg-type]


async def test_disabled_client_does_the_same_work_as_an_unknown_one() -> None:
    hasher = _Hasher()
    use_case = _use_case(_RaisingFactory(DatabaseDisabledError()), hasher)

    with pytest.raises(DatabaseDisabledError) as caught:
        await use_case.execute("JPEREZ@APAGADA", "x")

    assert isinstance(caught.value, InvalidCredentialsError)
    assert hasher.verified == 1
    assert "JPEREZ" not in caught.value.message


async def test_unreachable_client_propagates_from_the_user_lookup() -> None:
    use_case = _use_case(_RaisingFactory(None, _BrokenRepository()), _Hasher())

    with pytest.raises(DatabaseUnreachableError):
        await use_case.execute("JPEREZ@NORTE", "x")


class _OneDatabase:
    def __init__(self, database: ErpDatabase | None) -> None:
        self._database = database

    async def get_by_code(self, code: str) -> ErpDatabase | None:  # noqa: ARG002
        return self._database


@pytest.mark.parametrize(
    ("database", "expected"),
    [
        (ErpDatabase(code="APAGADA", is_active=False), DatabaseDisabledError),
        (ErpDatabase(code="ROTA", credentials_unreadable=True), DatabaseUnreachableError),
    ],
)
async def test_factory_tells_disabled_from_unreadable_credentials(
    database: ErpDatabase, expected: type[Exception]
) -> None:
    factory = ErpUserRepositoryFactory(
        _OneDatabase(database),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
    )

    with pytest.raises(expected):
        await factory.for_code(database.code)


async def test_factory_keeps_unregistered_and_deleted_codes_as_none() -> None:
    deleted = ErpDatabase(code="BORRADA", deleted_at=datetime.now(UTC))
    for stored in (None, deleted):
        factory = ErpUserRepositoryFactory(
            _OneDatabase(stored),  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
        )

        assert await factory.for_code("BORRADA") is None


async def test_erp_connection_failure_becomes_database_unreachable() -> None:
    from sqlalchemy.exc import OperationalError

    class _DeadEngine:
        def connect(self) -> object:
            raise OperationalError("SELECT 1", {}, OSError("refused"))

    repository = ErpUserRepository(_DeadEngine())  # type: ignore[arg-type]

    with pytest.raises(DatabaseUnreachableError):
        await repository.find_by_login("JPEREZ")


def test_a_wrong_password_keeps_the_generic_error(client: TestClient) -> None:
    response = client.post("/auth/login", json={"login": "JPEREZ@NORTE", "password": "x"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Usuario o contraseña inválidos"}


def test_unknown_client_code_still_counts_as_a_failed_attempt(client: TestClient) -> None:
    """Es un login fallido más: no abre una vía de intentos sin límite."""
    for _ in range(5):
        client.post("/auth/login", json={"login": "JPEREZ@NOEXISTE", "password": "x"})

    response = client.post("/auth/login", json={"login": "JPEREZ@NOEXISTE", "password": "x"})

    assert response.status_code == 429
