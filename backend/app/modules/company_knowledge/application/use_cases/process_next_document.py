import logging
from dataclasses import replace

from app.modules.company_knowledge.application.use_cases.read_pdf_pages import (
    PDF_MEDIA_TYPE,
    ReadPdfPagesUseCase,
)
from app.modules.company_knowledge.domain.entities.company_document import CompanyDocument
from app.modules.company_knowledge.domain.exceptions import (
    DocumentExtractionError,
    EmbedderUnavailableError,
)
from app.modules.company_knowledge.domain.interfaces import (
    DocumentIndex,
    DocumentProcessor,
    DocumentRepository,
    ProcessingOutcome,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentStatusCode,
)
from app.modules.company_knowledge.infrastructure.progress import (
    get_progress_registry,
)

logger = logging.getLogger(__name__)


class ProcessNextCompanyDocumentUseCase:
    """Toma el documento pendiente más antiguo y lo procesa.

    Lo invoca el worker en un bucle. Nunca loguea contenido: solo ids,
    estados y tamaños (RNF-07).
    """

    def __init__(
        self,
        repository: DocumentRepository,
        processor: DocumentProcessor,
        max_total_chunks: int,
        index: DocumentIndex | None = None,
        pdf_reader: ReadPdfPagesUseCase | None = None,
    ) -> None:
        self._repository = repository
        self._processor = processor
        self._max_total_chunks = max_total_chunks
        self._index = index
        # `None` (tests de la Fase 1) = el PDF se extrae como siempre, con
        # `pypdf` y sin guardar páginas.
        self._pdf_reader = pdf_reader

    async def execute(self) -> bool:
        """`True` si procesó un documento; `False` si no había trabajo.

        Levanta `EmbedderUnavailableError` después de devolver el documento a
        la cola: el worker decide cuánto esperar antes de reintentar.
        """
        document = await self._repository.claim_next_pending()
        if document is None:
            return False

        outcome = await self._run_pipeline(document)
        if outcome.status == DocumentStatus.READY:
            outcome = await self._enforce_installation_limit(outcome)

        # Cerrado el documento, el avance ya no aplica: dejarlo colgado haría
        # que la interfaz mostrara un porcentaje viejo para siempre.
        get_progress_registry().finish(document.id)

        completed = await self._repository.complete_processing(
            document.id, document.version, outcome
        )
        if not completed:
            # Eliminado o reemplazado mientras se procesaba: el resultado ya
            # no corresponde a ningún archivo vigente y se descarta.
            logger.info(
                "company_docs_processing_discarded document=%s version=%s",
                document.id,
                document.version,
            )
            return True

        logger.info(
            "company_docs_processed document=%s status=%s code=%s chunks=%s",
            document.id,
            outcome.status.value,
            outcome.status_code.value if outcome.status_code else None,
            len(outcome.chunks),
        )
        if self._index is not None:
            # `publish_document` sincroniza desde la BD: si ya no está `ready`
            # lo retira, así que sirve para los dos resultados.
            await self._index.publish_document(document.id)
        return True

    async def _run_pipeline(self, document: CompanyDocument) -> ProcessingOutcome:
        content = await self._repository.get_blob(document.id)
        if content is None:
            return ProcessingOutcome.failed(DocumentStatusCode.INTERNAL_ERROR)
        try:
            if self._pdf_reader is not None and document.media_type == PDF_MEDIA_TYPE:
                return await self._read_pdf(self._pdf_reader, document, content)
            return await self._processor.process(content, document.media_type, document.id)
        except EmbedderUnavailableError:
            await self._repository.release_claim(document.id, document.version)
            raise
        except Exception:
            logger.exception("company_docs_processing_failed document=%s", document.id)
            return ProcessingOutcome.failed(DocumentStatusCode.INTERNAL_ERROR)

    async def _read_pdf(
        self, reader: ReadPdfPagesUseCase, document: CompanyDocument, content: bytes
    ) -> ProcessingOutcome:
        try:
            reading = await reader.execute(document, content)
        except DocumentExtractionError as exc:
            return ProcessingOutcome.failed(exc.status_code)
        # El umbral de "parece escaneado" solo aplica si ninguna página la leyó
        # la IA: es la detección de siempre para la lectura con `pypdf`.
        outcome = await self._processor.process_pages(
            reading.extracted, document.id, detect_scanned=reading.ai_page_count == 0
        )
        if outcome.status == DocumentStatus.NO_TEXT and reading.ai_page_count > 0:
            outcome = replace(outcome, status_code=DocumentStatusCode.AI_UNREADABLE)
        elif outcome.status == DocumentStatus.NO_TEXT and reading.ai_failed_page_count > 0:
            # Sin este código el aviso sería "parece escaneado, leelo con IA",
            # y volver a intentarlo fallaría igual hasta corregir el proveedor.
            outcome = replace(outcome, status_code=DocumentStatusCode.AI_FAILED)
        return replace(
            outcome,
            reading_method=reading.reading_method,
            ai_page_count=reading.ai_page_count,
            ai_cost_usd=reading.ai_cost_usd,
        )

    async def _enforce_installation_limit(self, outcome: ProcessingOutcome) -> ProcessingOutcome:
        # `total_chunks` ya no cuenta los fragmentos previos de este documento:
        # reprocesar y reemplazar los borran antes de encolar.
        current = await self._repository.total_chunks()
        if current + len(outcome.chunks) > self._max_total_chunks:
            return ProcessingOutcome(
                status=DocumentStatus.FAILED,
                status_code=DocumentStatusCode.INDEX_LIMIT_REACHED,
                page_count=outcome.page_count,
                char_count=outcome.char_count,
                reading_method=outcome.reading_method,
                ai_page_count=outcome.ai_page_count,
                ai_cost_usd=outcome.ai_cost_usd,
            )
        return outcome
