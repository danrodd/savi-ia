"""Worker de fuentes web: rastrea de a una fuente, en segundo plano.

Como el worker de documentos: vive en el `lifespan`, duerme hasta que un
alta o un "refrescar ahora" lo despierta (con un timeout como red de
seguridad) y ninguna excepción lo detiene. Los refrescos automáticos solo
se encolan dentro de la ventana nocturna, para no competir con el chat en
horario de uso.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import datetime, time

from app.modules.company_knowledge.application.use_cases import CrawlWebSourceUseCase
from app.modules.company_knowledge.domain.interfaces import WebSourceRepository

logger = logging.getLogger(__name__)


def parse_window(value: str) -> tuple[time, time]:
    """`"01:00-05:00"` → (01:00, 05:00). Inválido → toda la noche por defecto."""
    try:
        start, end = (part.strip() for part in value.split("-", 1))
        return time.fromisoformat(start), time.fromisoformat(end)
    except ValueError:
        return time(1, 0), time(5, 0)


def in_window(now: time, window: tuple[time, time]) -> bool:
    start, end = window
    if start <= end:
        return start <= now < end
    return now >= start or now < end  # cruza la medianoche (22:00-04:00)


class WebSourceWorker:
    def __init__(
        self,
        *,
        repository: WebSourceRepository,
        use_case: CrawlWebSourceUseCase,
        refresh_window: str,
        idle_timeout_s: float = 300.0,
        error_backoff_s: float = 30.0,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._repository = repository
        self._use_case = use_case
        self._window = parse_window(refresh_window)
        self._idle_timeout_s = idle_timeout_s
        self._error_backoff_s = error_backoff_s
        self._clock = clock
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def notify(self) -> None:
        self._wakeup.set()

    async def start(self) -> None:
        # Un reinicio a mitad de un rastreo lo deja `crawling`: vuelve a la cola.
        requeued = await self._repository.requeue_crawling()
        if requeued:
            logger.info("company_web_worker_requeued sources=%s", requeued)
        self._task = asyncio.create_task(self._run(), name="company-web-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def run_once(self) -> bool:
        """Un ciclo: encola refrescos vencidos (en la ventana) y rastrea uno."""
        if in_window(self._clock().time(), self._window):
            await self._repository.enqueue_due_refreshes()
        return await self._use_case.execute()

    async def _run(self) -> None:
        while True:
            self._wakeup.clear()
            try:
                crawled = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("company_web_worker_unexpected_error")
                await self._sleep(self._error_backoff_s)
                continue
            if not crawled:
                await self._sleep(self._idle_timeout_s)

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wakeup.wait(), timeout=seconds)
