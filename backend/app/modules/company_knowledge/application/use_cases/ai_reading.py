"""Configuración de la lectura con IA y "Leer con IA" de un documento."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from app.modules.company_knowledge.application.use_cases.read_pdf_pages import PDF_MEDIA_TYPE
from app.modules.company_knowledge.application.use_cases.reprocess_document import (
    ReprocessCompanyDocumentUseCase,
)
from app.modules.company_knowledge.domain.entities.company_document import CompanyDocument
from app.modules.company_knowledge.domain.entities.page_reading import KnowledgeSettings
from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentConflictError,
    CompanyDocumentNotFoundError,
)
from app.modules.company_knowledge.domain.interfaces import (
    AiReaderAvailability,
    AiReaderProvider,
    DocumentIndex,
    DocumentPageRepository,
    DocumentRepository,
    KnowledgeSettingsRepository,
)
from app.modules.company_knowledge.domain.value_objects import DocumentStatus

# Tokens por página para estimar antes de tener lecturas reales. Salen del
# spike (`docs/company_knowledge/spike-lectura-ia.md`): Gemini cobra 258
# tokens fijos por página; Claude y OpenAI mandan texto e imagen.
_INPUT_TOKENS_PER_PAGE = {"claude": 3000, "openai": 3200, "gemini": 750}
_OUTPUT_TOKENS_PER_PAGE = 700
# Con estas credenciales Claude no cobra por token: consume el límite de la
# suscripción.
_SUBSCRIPTION_CREDENTIALS = ("local_session", "oauth_token")


@dataclass(frozen=True, slots=True)
class AiReadingStatus:
    enabled: bool
    available: bool
    provider: str | None
    model: str | None
    # Claude por sesión local o token OAuth: la lectura gasta la suscripción.
    uses_subscription: bool
    estimated_usd_per_page: float | None
    unavailable_reason: str | None
    updated_by_login: str | None
    updated_at: datetime | None
    # Activada pero sin aceptación para el proveedor activo: no se manda nada.
    consent_required: bool = False
    consent_provider: str | None = None
    consent_by_login: str | None = None
    consent_at: datetime | None = None


class _StatusBuilder:
    def __init__(
        self,
        settings: KnowledgeSettingsRepository,
        readers: AiReaderProvider,
        pages: DocumentPageRepository,
    ) -> None:
        self._settings = settings
        self._readers = readers
        self._pages = pages

    async def build(self, settings: KnowledgeSettings | None = None) -> AiReadingStatus:
        current = settings or await self._settings.get()
        availability = await self._readers.availability()
        return AiReadingStatus(
            enabled=current.ai_reading_enabled,
            available=availability.available,
            provider=availability.provider,
            model=availability.model,
            uses_subscription=(
                availability.provider == "claude"
                and availability.credential_kind in _SUBSCRIPTION_CREDENTIALS
            ),
            estimated_usd_per_page=await self._estimate(availability),
            unavailable_reason=availability.reason,
            updated_by_login=current.updated_by_login,
            updated_at=current.updated_at,
            consent_required=(
                current.ai_reading_enabled
                and availability.available
                and not current.allows_sending_to(availability.provider)
            ),
            consent_provider=current.consent_provider,
            consent_by_login=current.consent_by_login,
            consent_at=current.consent_at,
        )

    async def _estimate(self, availability: AiReaderAvailability) -> float | None:
        if not availability.available or not availability.provider or not availability.model:
            return None
        # Lo medido le gana a la estimación: es lo que de verdad cuesta con
        # los documentos de esta empresa.
        measured = await self._pages.average_cost_per_page(
            availability.provider, availability.model
        )
        if measured is not None:
            return measured
        if availability.input_price is None or availability.output_price is None:
            return None
        input_tokens = _INPUT_TOKENS_PER_PAGE.get(availability.provider, 3000)
        return (
            input_tokens * availability.input_price
            + _OUTPUT_TOKENS_PER_PAGE * availability.output_price
        ) / 1_000_000


class GetAiReadingSettingsUseCase:
    def __init__(
        self,
        settings: KnowledgeSettingsRepository,
        readers: AiReaderProvider,
        pages: DocumentPageRepository,
    ) -> None:
        self._status = _StatusBuilder(settings, readers, pages)

    async def execute(self) -> AiReadingStatus:
        return await self._status.build()


class UpdateAiReadingSettingsUseCase:
    def __init__(
        self,
        settings: KnowledgeSettingsRepository,
        readers: AiReaderProvider,
        pages: DocumentPageRepository,
    ) -> None:
        self._settings = settings
        self._readers = readers
        self._status = _StatusBuilder(settings, readers, pages)

    async def execute(
        self, *, enabled: bool, updated_by_login: str, accept_provider: str | None = None
    ) -> AiReadingStatus:
        """Activa o apaga la lectura con IA.

        Activarla exige haber aceptado el envío al proveedor ACTIVO: en este
        pedido (`accept_provider`) o antes. Si el aviso se aceptó para otro
        proveedor, no vale: el administrador tiene que volver a leerlo.
        """
        current = await self._settings.get()
        updated = replace(current, ai_reading_enabled=enabled, updated_by_login=updated_by_login)
        if enabled:
            provider = (await self._readers.availability()).provider
            if accept_provider is not None:
                if accept_provider != provider:
                    raise CompanyDocumentConflictError(
                        "El proveedor de IA cambió mientras revisabas el aviso. "
                        "Leelo de nuevo y volvé a aceptar."
                    )
                updated = replace(
                    updated,
                    consent_provider=provider,
                    consent_by_login=updated_by_login,
                    consent_at=datetime.now(UTC),
                )
            elif provider is None or current.consent_provider != provider:
                raise CompanyDocumentConflictError(
                    "Para activar la lectura con IA, aceptá el envío de los PDF al proveedor."
                )
        return await self._status.build(await self._settings.save(updated))


class ReadCompanyDocumentWithAiUseCase:
    """Vuelve a leer un PDF con IA: descarta lo leído y lo encola.

    Sirve para los documentos que quedaron "Sin texto" antes de la Fase 4 y
    para releer uno cuando cambió el modelo o el prompt.
    """

    def __init__(
        self,
        repository: DocumentRepository,
        pages: DocumentPageRepository,
        settings: KnowledgeSettingsRepository,
        readers: AiReaderProvider,
        enqueue_notifier: Callable[[], None] | None = None,
        index: DocumentIndex | None = None,
    ) -> None:
        self._repository = repository
        self._pages = pages
        self._settings = settings
        self._readers = readers
        self._reprocess = ReprocessCompanyDocumentUseCase(repository, enqueue_notifier, index)

    async def execute(self, document_id: UUID) -> CompanyDocument:
        document = await self._repository.get_by_id(document_id)
        if document is None or document.is_deleted:
            raise CompanyDocumentNotFoundError(str(document_id))
        if document.media_type != PDF_MEDIA_TYPE:
            raise CompanyDocumentConflictError("Solo los PDF se pueden leer con IA.")
        settings = await self._settings.get()
        if not settings.ai_reading_enabled:
            raise CompanyDocumentConflictError(
                "La lectura con IA está desactivada. Activala en la configuración de Conocimiento."
            )
        availability = await self._readers.availability()
        if not availability.available:
            raise CompanyDocumentConflictError(
                availability.reason or "No hay un proveedor de IA disponible para leer documentos."
            )
        if not settings.allows_sending_to(availability.provider):
            raise CompanyDocumentConflictError(
                "Nadie aceptó enviar los PDF al proveedor de IA activo. Revisá el aviso en la "
                "configuración de Conocimiento."
            )
        # Se valida antes de descartar páginas: borrarlas de un documento en
        # curso le quitaría lo que la lectura que está corriendo ya guardó.
        if document.status == DocumentStatus.PROCESSING:
            raise CompanyDocumentConflictError("El documento se está procesando.")
        await self._pages.delete_ai_pages(document.id, document.version)
        return await self._reprocess.execute(document.id)
