"""API de administración, descarga protegida y disponibilidad de fuentes."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.main as main_module
from app.infrastructure.config import get_settings
from app.modules.auth.application.use_cases import (
    DatabaseAccess,
    ResolveModulesForDatabaseUseCase,
)
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.auth.infrastructure.http.admin import require_company_admin
from app.modules.company_knowledge.application.use_cases import (
    DownloadCompanyDocumentUseCase,
    RepositorySourceAvailabilityResolver,
)
from app.modules.company_knowledge.domain.exceptions import CompanyDocumentNotFoundError
from app.modules.company_knowledge.domain.interfaces import ProcessingOutcome
from app.modules.company_knowledge.domain.services import DocumentAccessContext
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentVisibility,
)
from app.modules.company_knowledge.infrastructure.http.repository_dependency import (
    get_document_repository,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_document_repository import (  # noqa: E501
    SqlAlchemyDocumentRepository,
)
from app.modules.conversations.domain.entities import Conversation, Message, MessageRole
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.domain.value_objects import MessageSource
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.infrastructure.http.dependencies import (
    get_erp_database_repository,
)

from .conftest import make_document, make_pdf

BASE = uuid4()
ADMIN = AuthenticatedUser(
    id=1, login="ADMIN", full_name="Admin", is_admin=True, is_active=True, erp_database_id=BASE
)


class _ErpRepo:
    def __init__(self, known: set[UUID]) -> None:
        self._known = known

    async def get_by_id(self, database_id: UUID) -> ErpDatabase | None:
        return ErpDatabase(id=database_id) if database_id in self._known else None


@pytest.fixture
def client(
    sessionmaker_: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("COMPANY_DOCS_MAX_FILE_MB", "1")
    get_settings.cache_clear()
    app = main_module.create_app()
    repo = SqlAlchemyDocumentRepository(sessionmaker_)
    app.dependency_overrides[require_company_admin] = lambda: ADMIN
    app.dependency_overrides[get_document_repository] = lambda: repo
    app.dependency_overrides[get_erp_database_repository] = lambda: _ErpRepo({BASE})
    yield TestClient(app)  # sin `with`: no corre el lifespan
    get_settings.cache_clear()


def _upload(client: TestClient, content: bytes, name: str = "manual.md", **form: Any) -> Any:
    data = {"visibility": "all", **form}
    return client.post("/admin/company-documents", files={"file": (name, content)}, data=data)


def test_upload_creates_a_pending_document(client: TestClient) -> None:
    response = _upload(client, b"# Caja\n\nCierre diario.", title="Manual de caja")
    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["title"], body["media_type"]) == (
        "pending",
        "Manual de caja",
        "text/markdown",
    )
    assert "sha256" not in body


def test_duplicate_upload_points_to_the_existing_document(client: TestClient) -> None:
    first = _upload(client, b"mismo contenido").json()
    response = _upload(client, b"mismo contenido", name="copia.md")
    assert response.status_code == 409
    assert response.json()["existing_document_id"] == first["id"]


def test_oversized_upload_is_413(client: TestClient) -> None:
    response = _upload(client, b"a" * (1024 * 1024 + 10))
    assert (response.status_code, response.json()["errorCode"]) == (413, "file_too_large")


def test_binary_upload_is_415(client: TestClient) -> None:
    response = _upload(client, bytes(range(256)) * 8, name="virus.md")
    assert (response.status_code, response.json()["errorCode"]) == (415, "unsupported_media_type")


@pytest.mark.parametrize(
    "form",
    [
        {"visibility": "modules"},  # sin módulos
        {"visibility": "all", "modules": "VENTA"},  # módulos sin visibilidad por módulos
        {"visibility": "all", "all_databases": "false"},  # sin bases
        {
            "visibility": "all",
            "all_databases": "false",
            "database_ids": str(uuid4()),
        },  # base inexistente
        {"visibility": "modules", "modules": "NO_EXISTE"},
    ],
)
def test_inconsistent_permissions_are_422(client: TestClient, form: dict[str, str]) -> None:
    assert _upload(client, f"texto {uuid4()}".encode(), **form).status_code == 422


def test_patch_updates_permissions_and_delete_is_idempotent(client: TestClient) -> None:
    created = _upload(client, b"Politica de descuentos").json()
    patched = client.patch(
        f"/admin/company-documents/{created['id']}",
        json={"visibility": "modules", "modules": ["CONTABILIDAD"], "title": "Política"},
    )
    assert patched.status_code == 200
    assert (patched.json()["visibility"], patched.json()["modules"]) == (
        "modules",
        ["CONTABILIDAD"],
    )

    assert client.delete(f"/admin/company-documents/{created['id']}").status_code == 204
    assert client.delete(f"/admin/company-documents/{created['id']}").status_code == 204
    assert client.delete(f"/admin/company-documents/{uuid4()}").status_code == 404
    assert client.get(f"/admin/company-documents/{created['id']}").status_code == 404


def test_pdf_upload_is_detected_by_content(client: TestClient) -> None:
    response = _upload(client, make_pdf(["Texto"]), name="politica.txt")
    assert response.json()["media_type"] == "application/pdf"


def test_admin_endpoints_require_admin(sessionmaker_: async_sessionmaker[AsyncSession]) -> None:
    app = main_module.create_app()
    app.dependency_overrides[get_document_repository] = lambda: SqlAlchemyDocumentRepository(
        sessionmaker_
    )
    anonymous = TestClient(app)
    assert anonymous.get("/admin/company-documents").status_code == 401


# ── Descarga protegida ───────────────────────────────────────────────────


USER = AuthenticatedUser(
    id=7, login="JPEREZ", full_name="J", is_admin=False, is_active=True, erp_database_id=BASE
)


class _Conversations:
    def __init__(self, conversation: Conversation | None, messages: list[Message]) -> None:
        self._conversation = conversation
        self._messages = messages

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        return self._conversation

    async def list_messages(self, conversation_id: UUID, **_: Any) -> list[Message]:
        return self._messages


class _Access:
    def __init__(self, access: DatabaseAccess) -> None:
        self._access = access

    async def execute(
        self, login: str, database_id: UUID, *, identity: object = None
    ) -> DatabaseAccess:
        return self._access


async def _ready(
    repo: SqlAlchemyDocumentRepository, visibility: DocumentVisibility, content: bytes = b"hola"
) -> UUID:
    document = await repo.save(
        make_document(
            visibility=visibility,
            modules=[ModuleCode.CONTABILIDAD] if visibility == DocumentVisibility.MODULES else [],
        )
    )
    await repo.save_blob(document.id, content)
    claimed = await repo.claim_next_pending()
    assert claimed is not None
    await repo.complete_processing(
        document.id, 1, ProcessingOutcome(status=DocumentStatus.READY, embedding_model="m")
    )
    return document.id


def _download_use_case(
    repo: SqlAlchemyDocumentRepository,
    *,
    owner_id: int = 7,
    cites: UUID | None = None,
    access: DatabaseAccess | None = None,
) -> DownloadCompanyDocumentUseCase:
    conversation = Conversation(user_id=owner_id, erp_database_id=BASE, owner_erp_database_id=BASE)
    messages = []
    if cites is not None:
        messages.append(
            Message(
                role=MessageRole.ASSISTANT, sources=[MessageSource("D1", ("D1",), cites, 1, "Doc")]
            )
        )
    return DownloadCompanyDocumentUseCase(
        repository=repo,
        conversations=cast(ConversationRepository, _Conversations(conversation, messages)),
        access_resolver=cast(
            ResolveModulesForDatabaseUseCase,
            _Access(access or DatabaseAccess(has_access=True, modules=frozenset())),
        ),
        savi_admin_logins=frozenset(),
    )


async def test_download_succeeds_for_owner_citation_and_permission(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlAlchemyDocumentRepository(sessionmaker_)
    document_id = await _ready(repo, DocumentVisibility.ALL, b"contenido")
    _, content = await _download_use_case(repo, cites=document_id).execute(
        document_id, uuid4(), USER
    )
    assert content == b"contenido"


@pytest.mark.parametrize(
    "case", ["not_owner", "not_cited", "no_permission", "no_base_access", "deleted"]
)
async def test_every_rejection_is_not_found(
    sessionmaker_: async_sessionmaker[AsyncSession], case: str
) -> None:
    repo = SqlAlchemyDocumentRepository(sessionmaker_)
    visibility = DocumentVisibility.ADMINS if case == "no_permission" else DocumentVisibility.ALL
    document_id = await _ready(repo, visibility)
    kwargs: dict[str, Any] = {"cites": document_id}
    if case == "not_owner":
        kwargs["owner_id"] = 99
    if case == "not_cited":
        kwargs["cites"] = uuid4()
    if case == "no_base_access":
        kwargs["access"] = DatabaseAccess(has_access=False, modules=frozenset())
    if case == "deleted":
        await repo.soft_delete(document_id)
    with pytest.raises(CompanyDocumentNotFoundError):
        await _download_use_case(repo, **kwargs).execute(document_id, uuid4(), USER)


async def test_source_availability_reports_deleted_and_no_access(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = SqlAlchemyDocumentRepository(sessionmaker_)
    public = await _ready(repo, DocumentVisibility.ALL)
    secret = await _ready(repo, DocumentVisibility.ADMINS)
    gone = await _ready(repo, DocumentVisibility.ALL)
    await repo.soft_delete(gone)

    ctx = DocumentAccessContext(BASE, frozenset(), False, False)
    result = await RepositorySourceAvailabilityResolver(repo).resolve([public, secret, gone], ctx)

    assert result[public].available is True
    assert (result[secret].available, result[secret].reason) == (False, "no_access")
    assert (result[gone].available, result[gone].reason) == (False, "deleted")
