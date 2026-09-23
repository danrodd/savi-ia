"""Configuración de la lectura con IA, "Leer con IA" y sus endpoints."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.main as main_module
from app.infrastructure.config import get_settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.admin import require_company_admin
from app.modules.company_knowledge.application.responses import AiReadingSettingsResponse
from app.modules.company_knowledge.application.use_cases import (
    GetAiReadingSettingsUseCase,
    ReadCompanyDocumentWithAiUseCase,
    UpdateAiReadingSettingsUseCase,
)
from app.modules.company_knowledge.domain.entities.page_reading import (
    AiReadRecord,
    AiReadUsage,
    KnowledgeSettings,
    ReadPage,
)
from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentConflictError,
    CompanyDocumentNotFoundError,
)
from app.modules.company_knowledge.domain.interfaces import (
    AiReaderAvailability,
    AiReaderProvider,
    PdfPageReader,
)
from app.modules.company_knowledge.domain.value_objects import (
    AiReadOutcome,
    DocumentStatus,
    PageRoute,
)
from app.modules.company_knowledge.infrastructure.http.dependencies import (
    get_ai_reader_provider,
    get_knowledge_settings_repository,
    get_page_repository,
)
from app.modules.company_knowledge.infrastructure.http.repository_dependency import (
    get_document_repository,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_document_repository import (  # noqa: E501
    SqlAlchemyDocumentRepository,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_page_repository import (  # noqa: E501
    SqlAlchemyDocumentPageRepository,
    SqlAlchemyKnowledgeSettingsRepository,
)

from .conftest import make_document


class _Readers(AiReaderProvider):
    def __init__(self, availability: AiReaderAvailability) -> None:
        self._availability = availability

    async def availability(self) -> AiReaderAvailability:
        return self._availability

    async def build_reader(self) -> PdfPageReader | None:
        return None


def _available(
    provider: str = "openai",
    *,
    credential_kind: str = "api_key",
    input_price: float | None = 0.1,
    output_price: float | None = 0.5,
) -> AiReaderAvailability:
    return AiReaderAvailability(
        available=True,
        provider=provider,
        model="modelo-lectura",
        credential_kind=credential_kind,
        input_price=input_price,
        output_price=output_price,
    )


@pytest.fixture
def repos(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> tuple[
    SqlAlchemyDocumentRepository,
    SqlAlchemyDocumentPageRepository,
    SqlAlchemyKnowledgeSettingsRepository,
]:
    return (
        SqlAlchemyDocumentRepository(sessionmaker_),
        SqlAlchemyDocumentPageRepository(sessionmaker_),
        SqlAlchemyKnowledgeSettingsRepository(sessionmaker_),
    )


# ── Configuración ──────────────────────────────────────────────────────────


async def test_ai_reading_is_on_by_default_and_estimates_from_prices(
    repos: tuple[
        SqlAlchemyDocumentRepository,
        SqlAlchemyDocumentPageRepository,
        SqlAlchemyKnowledgeSettingsRepository,
    ],
) -> None:
    _, pages, settings = repos
    status = await GetAiReadingSettingsUseCase(settings, _Readers(_available()), pages).execute()

    assert (status.enabled, status.available, status.model) == (True, True, "modelo-lectura")
    assert status.estimated_usd_per_page == pytest.approx((3200 * 0.1 + 700 * 0.5) / 1e6)
    assert status.uses_subscription is False


async def test_measured_cost_beats_the_estimate(
    repos: tuple[
        SqlAlchemyDocumentRepository,
        SqlAlchemyDocumentPageRepository,
        SqlAlchemyKnowledgeSettingsRepository,
    ],
) -> None:
    _, pages, settings = repos
    await pages.record_ai_read(
        AiReadRecord(
            document_id=uuid4(),
            version=1,
            page_from=1,
            page_to=4,
            provider="openai",
            model="modelo-lectura",
            outcome=AiReadOutcome.OK,
            uploaded_by_login="ADMIN",
            uploaded_by_database_id=None,
            usage=AiReadUsage(input_tokens=1, output_tokens=1, cost_usd=0.02),
        )
    )

    status = await GetAiReadingSettingsUseCase(settings, _Readers(_available()), pages).execute()

    assert status.estimated_usd_per_page == pytest.approx(0.005)


async def test_without_prices_there_is_no_estimate_and_claude_session_warns(
    repos: tuple[
        SqlAlchemyDocumentRepository,
        SqlAlchemyDocumentPageRepository,
        SqlAlchemyKnowledgeSettingsRepository,
    ],
) -> None:
    _, pages, settings = repos
    readers = _Readers(
        _available("claude", credential_kind="local_session", input_price=None, output_price=None)
    )

    status = await GetAiReadingSettingsUseCase(settings, readers, pages).execute()

    assert status.estimated_usd_per_page is None
    assert status.uses_subscription is True


async def test_turning_it_off_is_saved_with_who_did_it(
    repos: tuple[
        SqlAlchemyDocumentRepository,
        SqlAlchemyDocumentPageRepository,
        SqlAlchemyKnowledgeSettingsRepository,
    ],
) -> None:
    _, pages, settings = repos
    use_case = UpdateAiReadingSettingsUseCase(settings, _Readers(_available()), pages)

    status = await use_case.execute(enabled=False, updated_by_login="ADMIN")

    assert (status.enabled, status.updated_by_login) == (False, "ADMIN")
    assert (await settings.get()).ai_reading_enabled is False


def test_privacy_notice_names_the_provider() -> None:
    from app.modules.company_knowledge.application.use_cases import AiReadingStatus

    response = AiReadingSettingsResponse.from_status(
        AiReadingStatus(
            enabled=True,
            available=True,
            provider="gemini",
            model="m",
            uses_subscription=False,
            estimated_usd_per_page=None,
            unavailable_reason=None,
            updated_by_login=None,
            updated_at=None,
        )
    )
    assert response.provider_name == "Gemini"
    assert "se envían a Gemini" in response.privacy_notice


# ── Leer con IA ────────────────────────────────────────────────────────────


async def test_read_with_ai_discards_ai_pages_and_requeues(
    repos: tuple[
        SqlAlchemyDocumentRepository,
        SqlAlchemyDocumentPageRepository,
        SqlAlchemyKnowledgeSettingsRepository,
    ],
) -> None:
    documents, pages, settings = repos
    document = await documents.save(
        make_document(media_type="application/pdf", status=DocumentStatus.NO_TEXT)
    )
    await pages.save_pages(
        document.id,
        1,
        [
            ReadPage(page_number=1, method=PageRoute.AI, text="leída"),
            ReadPage(page_number=2, method=PageRoute.TEXT, text="texto"),
        ],
    )
    notified: list[int] = []
    use_case = ReadCompanyDocumentWithAiUseCase(
        documents, pages, settings, _Readers(_available()), lambda: notified.append(1)
    )

    result = await use_case.execute(document.id)

    assert result.status == DocumentStatus.PENDING
    assert [p.method for p in await pages.list_pages(document.id, 1)] == [PageRoute.TEXT]
    assert notified == [1]


async def test_read_with_ai_rejects_what_it_cannot_read(
    repos: tuple[
        SqlAlchemyDocumentRepository,
        SqlAlchemyDocumentPageRepository,
        SqlAlchemyKnowledgeSettingsRepository,
    ],
) -> None:
    documents, pages, settings = repos
    markdown = await documents.save(make_document())
    pdf = await documents.save(make_document(media_type="application/pdf"))
    processing = await documents.save(
        make_document(media_type="application/pdf", status=DocumentStatus.PROCESSING)
    )
    use_case = ReadCompanyDocumentWithAiUseCase(documents, pages, settings, _Readers(_available()))

    with pytest.raises(CompanyDocumentNotFoundError):
        await use_case.execute(uuid4())
    with pytest.raises(CompanyDocumentConflictError, match="Solo los PDF"):
        await use_case.execute(markdown.id)
    with pytest.raises(CompanyDocumentConflictError, match="se está procesando"):
        await use_case.execute(processing.id)

    unavailable = ReadCompanyDocumentWithAiUseCase(
        documents,
        pages,
        settings,
        _Readers(AiReaderAvailability(available=False, reason="Sin proveedor activo.")),
    )
    with pytest.raises(CompanyDocumentConflictError, match="Sin proveedor activo"):
        await unavailable.execute(pdf.id)

    await settings.save(KnowledgeSettings(ai_reading_enabled=False))
    with pytest.raises(CompanyDocumentConflictError, match="desactivada"):
        await use_case.execute(pdf.id)


# ── Endpoints ──────────────────────────────────────────────────────────────

ADMIN = AuthenticatedUser(
    id=1, login="ADMIN", full_name="Admin", is_admin=True, is_active=True, erp_database_id=uuid4()
)


@pytest.fixture
def client(
    repos: tuple[
        SqlAlchemyDocumentRepository,
        SqlAlchemyDocumentPageRepository,
        SqlAlchemyKnowledgeSettingsRepository,
    ],
) -> Iterator[TestClient]:
    documents, pages, settings = repos
    get_settings.cache_clear()
    app = main_module.create_app()
    app.dependency_overrides[require_company_admin] = lambda: ADMIN
    app.dependency_overrides[get_document_repository] = lambda: documents
    app.dependency_overrides[get_page_repository] = lambda: pages
    app.dependency_overrides[get_knowledge_settings_repository] = lambda: settings
    app.dependency_overrides[get_ai_reader_provider] = lambda: _Readers(_available())
    yield TestClient(app)  # sin `with`: no corre el lifespan
    get_settings.cache_clear()


def test_get_and_put_ai_reading_settings(client: TestClient) -> None:
    body = client.get("/admin/company-documents/ai-reading").json()
    assert (body["ai_reading_enabled"], body["available"], body["provider_name"]) == (
        True,
        True,
        "OpenAI",
    )
    assert body["estimated_usd_per_page"] > 0

    response = client.put("/admin/company-documents/ai-reading", json={"ai_reading_enabled": False})
    assert response.status_code == 200
    assert (response.json()["ai_reading_enabled"], response.json()["updated_by_login"]) == (
        False,
        "ADMIN",
    )


def test_ai_reading_settings_require_an_admin(
    repos: tuple[
        SqlAlchemyDocumentRepository,
        SqlAlchemyDocumentPageRepository,
        SqlAlchemyKnowledgeSettingsRepository,
    ],
) -> None:
    _, pages, settings = repos
    get_settings.cache_clear()
    app = main_module.create_app()
    # Todo real salvo la persistencia: la autenticación es lo que se prueba.
    app.dependency_overrides[get_page_repository] = lambda: pages
    app.dependency_overrides[get_knowledge_settings_repository] = lambda: settings
    app.dependency_overrides[get_ai_reader_provider] = lambda: _Readers(_available())
    anonymous = TestClient(app)
    assert anonymous.get("/admin/company-documents/ai-reading").status_code == 401
    assert (
        anonymous.put(
            "/admin/company-documents/ai-reading", json={"ai_reading_enabled": False}
        ).status_code
        == 401
    )
    get_settings.cache_clear()


async def test_read_with_ai_endpoint_returns_the_pending_document(
    client: TestClient,
    repos: tuple[
        SqlAlchemyDocumentRepository,
        SqlAlchemyDocumentPageRepository,
        SqlAlchemyKnowledgeSettingsRepository,
    ],
) -> None:
    documents, _, _ = repos
    document = await documents.save(
        make_document(media_type="application/pdf", status=DocumentStatus.NO_TEXT)
    )

    response = client.post(f"/admin/company-documents/{document.id}/read-with-ai")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert {"reading_method", "ai_page_count", "ai_cost_usd", "progress_stage"} <= set(body)
