"""Worker de ingesta: procesa documentos pendientes en segundo plano.

Vive en el `lifespan` (un solo proceso por instalación). Toma documentos
de a uno; si no hay trabajo espera a que una subida lo despierte, con un
timeout como red de seguridad. Ninguna excepción lo detiene: un documento
problemático no puede dejar a la instalación sin procesar los demás.
"""

import asyncio
import contextlib
import logging

from app.modules.company_knowledge.application.use_cases import (
    ProcessNextCompanyDocumentUseCase,
)
from app.modules.company_knowledge.domain.exceptions import EmbedderUnavailableError
from app.modules.company_knowledge.domain.interfaces import DocumentRepository

logger = logging.getLogger(__name__)


class CompanyDocumentWorker:
    def __init__(
        self,
        *,
        repository: DocumentRepository,
        use_case: ProcessNextCompanyDocumentUseCase,
        embedding_model: str,
        idle_timeout_s: float = 60.0,
        unavailable_retry_s: float = 60.0,
        error_backoff_s: float = 5.0,
    ) -> None:
        self._repository = repository
        self._use_case = use_case
        self._embedding_model = embedding_model
        self._idle_timeout_s = idle_timeout_s
        self._unavailable_retry_s = unavailable_retry_s
        self._error_backoff_s = error_backoff_s
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def notify(self) -> None:
        """Despierta al worker (lo llaman subir, reemplazar y reprocesar)."""
        self._wakeup.set()

    async def start(self) -> None:
        # Un reinicio a mitad de procesamiento deja documentos `processing`
        # que nadie va a terminar: vuelven a la cola.
        requeued = await self._repository.requeue_processing()
        stale = await self._repository.enqueue_stale_embedding_documents(self._embedding_model)
        if requeued or stale:
            logger.info(
                "company_docs_worker_requeued processing=%s stale_model=%s", requeued, stale
            )
        self._task = asyncio.create_task(self._run(), name="company-docs-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            # Se limpia ANTES de buscar trabajo: una subida que llegue durante
            # `execute` deja el evento puesto y el próximo `wait` no duerme.
            self._wakeup.clear()
            try:
                processed = await self._use_case.execute()
            except asyncio.CancelledError:
                raise
            except EmbedderUnavailableError:
                logger.warning("company_docs_worker_embedder_unavailable")
                await self._sleep(self._unavailable_retry_s)
                continue
            except Exception:
                logger.exception("company_docs_worker_unexpected_error")
                await self._sleep(self._error_backoff_s)
                continue
            if not processed:
                await self._sleep(self._idle_timeout_s)

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wakeup.wait(), timeout=seconds)
