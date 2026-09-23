"""`/auth/me/bootstrap` resuelve contra la base del usuario (Fase 3, M1).

Antes usaba un resolver atado a la base POR DEFECTO: un usuario de otra base
recibía los módulos del usuario con el **mismo `idUsuario`** allá. El chat
nunca tuvo el problema (usa `ResolveModulesForDatabaseUseCase`), así que la
interfaz mostraba un conjunto de módulos y el agente aplicaba otro.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.auth.application.use_cases.resolve_modules_for_database import (
    DatabaseAccess,
)
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.value_objects import ModuleCode
from app.modules.auth.infrastructure.http import router as auth_router
from app.modules.auth.infrastructure.http.dependencies import get_current_user
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.infrastructure.http.dependencies import (
    get_erp_database_repository,
    get_resolve_modules_for_database_use_case,
)
from app.shared.exceptions import register_exception_handlers

BASE_DEL_USUARIO = uuid4()
USUARIO = AuthenticatedUser(
    id=5,
    erp_database_id=BASE_DEL_USUARIO,
    login="JPEREZ",
    full_name="J Pérez",
    is_admin=False,
    is_active=True,
)
BASE = ErpDatabase(id=BASE_DEL_USUARIO, code="FRAMI", name="frami")


class _BasesFalsas:
    """Registro de bases en memoria: la ruta solo lee código y nombre."""

    def __init__(self, *bases: ErpDatabase) -> None:
        self._bases = {b.id: b for b in bases}

    async def get_by_id(self, database_id: UUID) -> ErpDatabase | None:
        return self._bases.get(database_id)


class _ResolverFalso:
    """Registra con qué base y login lo llamaron."""

    def __init__(self) -> None:
        self.llamadas: list[tuple[str, object]] = []

    async def execute(self, login: str, database_id: object) -> DatabaseAccess:
        self.llamadas.append((login, database_id))
        return DatabaseAccess(
            has_access=True,
            modules=frozenset({ModuleCode.VENTA}),
            user_id_in_database=5,
            is_admin_in_database=False,
            version="hash-de-la-base-del-usuario",
        )


@pytest.fixture
def resolver() -> _ResolverFalso:
    return _ResolverFalso()


@pytest.fixture
def client(resolver: _ResolverFalso) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)
    app.dependency_overrides[get_current_user] = lambda: USUARIO
    app.dependency_overrides[get_resolve_modules_for_database_use_case] = lambda: resolver
    app.dependency_overrides[get_erp_database_repository] = lambda: _BasesFalsas(BASE)
    yield TestClient(app)


def test_bootstrap_resolves_against_the_user_database(
    client: TestClient, resolver: _ResolverFalso
) -> None:
    response = client.get("/auth/me/bootstrap")

    assert response.status_code == 200
    assert resolver.llamadas == [("JPEREZ", BASE_DEL_USUARIO)]


def test_bootstrap_returns_the_modules_of_that_database(
    client: TestClient,
) -> None:
    body = client.get("/auth/me/bootstrap").json()

    assert body["modules"] == [ModuleCode.VENTA.value]
    assert body["version"] == "hash-de-la-base-del-usuario"


def test_modules_version_resolves_against_the_user_database(
    client: TestClient, resolver: _ResolverFalso
) -> None:
    response = client.get("/auth/me/modules-version")

    assert response.status_code == 200
    assert response.json()["version"] == "hash-de-la-base-del-usuario"
    assert resolver.llamadas == [("JPEREZ", BASE_DEL_USUARIO)]


def test_bootstrap_says_which_database_the_session_is_in(client: TestClient) -> None:
    """La interfaz muestra "estás en FRAMI" y distingue al usuario de sus
    homónimos en otros clientes: el `idUsuario` se repite entre bases."""
    body = client.get("/auth/me/bootstrap").json()

    assert body["user"]["erp_database"] == {
        "id": str(BASE_DEL_USUARIO),
        "code": "FRAMI",
        "name": "frami",
    }


def test_me_says_which_database_the_session_is_in(client: TestClient) -> None:
    assert client.get("/auth/me").json()["erp_database"]["code"] == "FRAMI"
