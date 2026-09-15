"""`/auth/me/bootstrap` resuelve contra la base del usuario (Fase 3, M1).

Antes usaba un resolver atado a la base POR DEFECTO: un usuario de otra base
recibía los módulos del usuario con el **mismo `idUsuario`** allá. El chat
nunca tuvo el problema (usa `ResolveModulesForDatabaseUseCase`), así que la
interfaz mostraba un conjunto de módulos y el agente aplicaba otro.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

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
from app.modules.erp_databases.infrastructure.http.dependencies import (
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
