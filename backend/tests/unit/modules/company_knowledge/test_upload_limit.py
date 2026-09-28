"""Cupo de subidas configurable desde la pantalla de Conocimiento."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.main as main_module
from app.infrastructure.config import get_settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.admin import require_company_admin
from app.modules.company_knowledge.infrastructure.http.dependencies import (
    get_knowledge_settings_repository,
)
from app.modules.company_knowledge.infrastructure.http.repository_dependency import (
    get_document_repository,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_document_repository import (  # noqa: E501
    SqlAlchemyDocumentRepository,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_page_repository import (  # noqa: E501
    SqlAlchemyKnowledgeSettingsRepository,
)
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.infrastructure.http.dependencies import (
    get_erp_database_repository,
)
from app.shared.exceptions import RateLimitExceededError
from app.shared.rate_limit import effective_upload_limit, enforce_upload_limits


class _ErpRepo:
    async def get_by_id(self, database_id: UUID) -> ErpDatabase | None:
        return ErpDatabase(id=database_id)


def _admin() -> AuthenticatedUser:
    # Base nueva por test: el limitador es de proceso y la clave incluye la
    # base, así ningún test comparte cupo con otro.
    return AuthenticatedUser(
        id=7,
        login="ADMIN",
        full_name="Admin",
        is_admin=True,
        is_active=True,
        erp_database_id=uuid4(),
    )


@pytest.fixture
def client(
    sessionmaker_: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_UPLOAD_PER_HOUR", "30")
    monkeypatch.setenv("RATE_LIMIT_UPLOAD_PER_HOUR_MAX", "500")
    get_settings.cache_clear()
    app = main_module.create_app()
    documents = SqlAlchemyDocumentRepository(sessionmaker_)
    knowledge_settings = SqlAlchemyKnowledgeSettingsRepository(sessionmaker_)
    admin = _admin()
    app.dependency_overrides[require_company_admin] = lambda: admin
    app.dependency_overrides[get_document_repository] = lambda: documents
    app.dependency_overrides[get_knowledge_settings_repository] = lambda: knowledge_settings
    app.dependency_overrides[get_erp_database_repository] = lambda: _ErpRepo()
    yield TestClient(app)  # sin `with`: no corre el lifespan
    get_settings.cache_clear()


def test_without_a_value_the_server_default_applies(client: TestClient) -> None:
    body = client.get("/admin/company-documents/upload-limit").json()

    assert body["upload_limit_per_hour"] is None
    assert (body["default"], body["maximum"], body["effective"]) == (30, 500, 30)


def test_an_admin_raises_the_limit_and_it_persists(client: TestClient) -> None:
    saved = client.put("/admin/company-documents/upload-limit", json={"upload_limit_per_hour": 120})

    assert saved.status_code == 200
    assert saved.json()["effective"] == 120
    body = client.get("/admin/company-documents/upload-limit").json()
    assert (body["upload_limit_per_hour"], body["updated_by_login"]) == (120, "ADMIN")


@pytest.mark.parametrize("value", [0, 501])
def test_values_outside_the_server_range_are_rejected(client: TestClient, value: int) -> None:
    response = client.put(
        "/admin/company-documents/upload-limit", json={"upload_limit_per_hour": value}
    )

    assert response.status_code == 422


def test_null_goes_back_to_the_server_default(client: TestClient) -> None:
    client.put("/admin/company-documents/upload-limit", json={"upload_limit_per_hour": 120})

    body = client.put(
        "/admin/company-documents/upload-limit", json={"upload_limit_per_hour": None}
    ).json()

    assert (body["upload_limit_per_hour"], body["effective"]) == (None, 30)


def test_uploads_follow_the_configured_limit(client: TestClient) -> None:
    client.put("/admin/company-documents/upload-limit", json={"upload_limit_per_hour": 1})

    def upload(name: str) -> int:
        return client.post(
            "/admin/company-documents",
            files={"file": (name, f"# {name}\n\nContenido de prueba.".encode())},
            data={"visibility": "all"},
        ).status_code

    assert upload("uno.md") == 201
    assert upload("dos.md") == 429


def test_the_effective_limit_never_exceeds_the_server_ceiling() -> None:
    settings = get_settings().model_copy(
        update={"rate_limit_upload_per_hour": 30, "rate_limit_upload_per_hour_max": 100}
    )

    assert effective_upload_limit(settings, None) == 30
    assert effective_upload_limit(settings, 80) == 80
    # Un valor viejo guardado con un techo mayor no lo supera.
    assert effective_upload_limit(settings, 5000) == 100


def test_the_guard_blocks_after_the_configured_quota() -> None:
    settings = get_settings().model_copy(update={"rate_limit_enabled": True})
    user = _admin()

    enforce_upload_limits(settings, user, 2)
    enforce_upload_limits(settings, user, 2)
    with pytest.raises(RateLimitExceededError):
        enforce_upload_limits(settings, user, 2)
