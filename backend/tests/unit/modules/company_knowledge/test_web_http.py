"""Endpoints de fuentes web (Fase 5)."""

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
from app.modules.company_knowledge.infrastructure.http import web_routes
from app.modules.company_knowledge.infrastructure.http.dependencies import (
    get_knowledge_settings_repository,
)
from app.modules.company_knowledge.infrastructure.http.repository_dependency import (
    get_document_repository,
)
from app.modules.company_knowledge.infrastructure.http.web_dependencies import (
    get_web_fetcher,
    get_web_source_repository,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_document_repository import (  # noqa: E501
    SqlAlchemyDocumentRepository,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_page_repository import (  # noqa: E501
    SqlAlchemyKnowledgeSettingsRepository,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_web_source_repository import (  # noqa: E501
    SqlAlchemyWebSourceRepository,
)
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.infrastructure.http.dependencies import (
    get_erp_database_repository,
)

from .test_web_sources import ROOT, FakeSite, _long, _page, _sitemap

BASE = uuid4()
OTHER = uuid4()
ADMIN = AuthenticatedUser(
    id=1, login="ADMIN", full_name="Admin", is_admin=True, is_active=True, erp_database_id=BASE
)


class _ErpRepo:
    async def get_by_id(self, database_id: UUID) -> ErpDatabase | None:
        return ErpDatabase(id=database_id) if database_id in {BASE, OTHER} else None


@pytest.fixture
def site() -> FakeSite:
    site = FakeSite()
    site.set("sitemap.xml", 200, _sitemap("planes"), content_type="application/xml")
    site.set("", 200, _page("Inicio", _long("Somos una ferretería con tres sedes.")))
    site.set("planes", 200, _page("Planes", _long("El plan Pro cuesta $20 al mes.")))
    return site


def _client(
    sessionmaker_: async_sessionmaker[AsyncSession],
    site: FakeSite,
    monkeypatch: pytest.MonkeyPatch,
    *,
    platform_admin: bool,
) -> TestClient:
    get_settings.cache_clear()
    app = main_module.create_app()
    sources = SqlAlchemyWebSourceRepository(sessionmaker_)
    documents = SqlAlchemyDocumentRepository(sessionmaker_)
    app.dependency_overrides[require_company_admin] = lambda: ADMIN
    app.dependency_overrides[get_web_source_repository] = lambda: sources
    app.dependency_overrides[get_document_repository] = lambda: documents
    knowledge_settings = SqlAlchemyKnowledgeSettingsRepository(sessionmaker_)
    app.dependency_overrides[get_knowledge_settings_repository] = lambda: knowledge_settings
    app.dependency_overrides[get_web_fetcher] = lambda: site
    app.dependency_overrides[get_erp_database_repository] = lambda: _ErpRepo()

    async def _platform(_user: AuthenticatedUser, _settings: object) -> bool:
        return platform_admin

    monkeypatch.setattr(web_routes, "is_platform_admin", _platform)
    return TestClient(app)  # sin `with`: no corre el lifespan


@pytest.fixture
def client(
    sessionmaker_: async_sessionmaker[AsyncSession], site: FakeSite, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    yield _client(sessionmaker_, site, monkeypatch, platform_admin=True)
    get_settings.cache_clear()


URL = "/admin/company-web-sources"


def test_preview_shows_what_savi_would_learn(client: TestClient) -> None:
    response = client.post(f"{URL}/preview", json={"url": ROOT, "mode": "site"})

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Inicio"
    assert "ferretería" in body["sample"]
    assert (body["page_count"], body["used_sitemap"]) == (2, True)
    assert body["sections"] == {"sitemap.xml": 1}


def test_preview_rejects_a_site_that_forbids_robots(client: TestClient, site: FakeSite) -> None:
    site.disallow.add(ROOT)
    response = client.post(f"{URL}/preview", json={"url": ROOT})
    assert response.status_code == 422
    assert "robots" in response.json()["detail"]


def test_create_list_get_update_refresh_and_delete(client: TestClient) -> None:
    created = client.post(
        URL, json={"url": ROOT, "title": "Sitio de la empresa", "refresh": "daily"}
    )
    assert created.status_code == 201
    source = created.json()
    assert (source["status"], source["title"], source["refresh"]) == (
        "pending",
        "Sitio de la empresa",
        "daily",
    )

    assert [s["id"] for s in client.get(URL).json()] == [source["id"]]
    detail = client.get(f"{URL}/{source['id']}").json()
    assert detail["pages"] == []

    patched = client.patch(
        f"{URL}/{source['id']}", json={"visibility": "modules", "modules": ["INVENTARIO"]}
    )
    assert patched.status_code == 200 and patched.json()["modules"] == ["INVENTARIO"]

    # Sigue `pending` (nadie la rastreó): refrescar ahora es un conflicto.
    assert client.post(f"{URL}/{source['id']}/refresh").status_code == 409

    assert client.delete(f"{URL}/{source['id']}").status_code == 204
    assert client.get(URL).json() == []
    assert client.get(f"{URL}/{source['id']}").status_code == 404
    assert client.delete(f"{URL}/{source['id']}").status_code == 204  # idempotente


def test_an_internal_url_is_rejected_on_create(client: TestClient) -> None:
    response = client.post(URL, json={"url": "http://interno.test/admin"})
    assert response.status_code == 422


def test_invalid_permissions_are_rejected(client: TestClient) -> None:
    response = client.post(URL, json={"url": ROOT, "visibility": "modules", "modules": []})
    assert response.status_code == 422


def test_a_company_admin_only_sees_sources_that_apply_to_its_base(
    sessionmaker_: async_sessionmaker[AsyncSession], site: FakeSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = _client(sessionmaker_, site, monkeypatch, platform_admin=True)
    mine = platform.post(
        URL, json={"url": ROOT, "all_databases": False, "database_ids": [str(BASE)]}
    )
    other = platform.post(
        URL, json={"url": f"{ROOT}otra", "all_databases": False, "database_ids": [str(OTHER)]}
    )
    everyone = platform.post(URL, json={"url": f"{ROOT}todas"})

    company = _client(sessionmaker_, site, monkeypatch, platform_admin=False)
    visible = {s["id"] for s in company.get(URL).json()}

    assert visible == {mine.json()["id"], everyone.json()["id"]}
    assert company.get(f"{URL}/{other.json()['id']}").status_code == 404
    get_settings.cache_clear()


def test_web_sources_require_an_admin(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    get_settings.cache_clear()
    app = main_module.create_app()
    app.dependency_overrides[get_web_source_repository] = lambda: SqlAlchemyWebSourceRepository(
        sessionmaker_
    )
    # Todo real salvo la persistencia: la autenticación es lo que se prueba.
    app.dependency_overrides[get_erp_database_repository] = lambda: _ErpRepo()
    app.dependency_overrides[get_web_fetcher] = lambda: FakeSite()
    anonymous = TestClient(app)
    assert anonymous.get(URL).status_code == 401
    assert anonymous.post(URL, json={"url": ROOT}).status_code == 401
    get_settings.cache_clear()
