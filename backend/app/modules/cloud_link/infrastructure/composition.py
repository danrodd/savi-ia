"""Raíz de composición del módulo: arma los casos de uso con sus adaptadores.

Un solo conjunto de servicios por proceso (los lotes pendientes y los tamaños
de lote reducidos viven en el caso de uso de envío). El lifespan lo crea y las
rutas de administración lo consumen.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.infrastructure.config import Settings
from app.modules.cloud_link.application.heartbeat_payload import HeartbeatPayloadBuilder
from app.modules.cloud_link.application.pseudonymizer import PseudonymizerProvider
from app.modules.cloud_link.application.use_cases import (
    LinkInstanceUseCase,
    PreviewPayloadUseCase,
    RotateCredentialsUseCase,
    SendHeartbeatUseCase,
    SyncStreamsUseCase,
    UnlinkInstanceUseCase,
)
from app.modules.cloud_link.domain.entities import CloudLinkState, StreamWatermark
from app.modules.cloud_link.domain.interfaces import (
    CloudApi,
    CloudLinkRepository,
    InstanceInfoProvider,
    LocalTelemetry,
    SyncLock,
)
from app.modules.cloud_link.infrastructure.http_cloud_api import HttpxCloudApi
from app.modules.cloud_link.infrastructure.persistence import SqlAlchemyCloudLinkRepository
from app.modules.cloud_link.infrastructure.sources import (
    ConversationSource,
    DatabaseSource,
    FreeQuerySource,
    SessionSource,
    TurnSource,
)
from app.modules.cloud_link.infrastructure.sync_lock import NoopSyncLock, PostgresAdvisorySyncLock
from app.modules.cloud_link.infrastructure.system_info import (
    SqlAlchemyLocalTelemetry,
    SystemInstanceInfoProvider,
)
from app.shared.security import FernetCredentialCipher

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class CloudLinkServices:
    settings: Settings
    repository: CloudLinkRepository
    cloud_api: CloudApi
    sync_lock: SyncLock
    link: LinkInstanceUseCase
    unlink: UnlinkInstanceUseCase
    heartbeat: SendHeartbeatUseCase
    sync: SyncStreamsUseCase
    rotate: RotateCredentialsUseCase
    preview: PreviewPayloadUseCase
    _background: set[asyncio.Task[None]] = field(default_factory=set[asyncio.Task[None]])
    # Lo despierta el scheduler (si corre) para adelantar el próximo ciclo.
    on_wake: Callable[[], None] | None = None

    @property
    def sync_enabled(self) -> bool:
        return self.settings.savi_cloud_sync_enabled

    @property
    def cloud_configured(self) -> bool:
        return bool(self.settings.savi_cloud_url.strip())

    @property
    def allow_insecure_http(self) -> bool:
        return self.settings.app_env == "development"

    async def status(self) -> tuple[CloudLinkState, list[StreamWatermark]]:
        return await self.repository.get(), await self.repository.list_watermarks()

    async def run_sync_cycle(self) -> bool:
        """Un ciclo de envío bajo el lock. `False` si otro proceso lo tenía."""
        async with self.sync_lock.acquire() as acquired:
            if not acquired:
                return False
            await self.sync.execute()
            return True

    async def run_now(self) -> None:
        """Heartbeat y ciclo de envío inmediatos (`POST /sync-now`)."""
        try:
            await self.heartbeat.execute()
            await self.run_sync_cycle()
        except Exception:
            logger.exception("Falló la sincronización inmediata con SAVI Cloud.")

    def request_sync_now(self) -> None:
        """Lanza `run_now` en segundo plano y devuelve enseguida."""
        task = asyncio.create_task(self.run_now())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def drain_background(self) -> None:
        """Espera las tareas lanzadas por `request_sync_now` (tests, cierre)."""
        pending = list(self._background)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def wake(self) -> None:
        if self.on_wake is not None:
            self.on_wake()


def build_cloud_link_services(
    *,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    cipher: FernetCredentialCipher | None = None,
    cloud_api: CloudApi | None = None,
    engine: AsyncEngine | None = None,
    sync_lock: SyncLock | None = None,
    info_provider: InstanceInfoProvider | None = None,
    telemetry: LocalTelemetry | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> CloudLinkServices:
    cipher = cipher or FernetCredentialCipher(
        settings.erp_credentials_key, old_keys=[settings.erp_credentials_key_old]
    )
    allow_http = settings.app_env == "development"
    repository = SqlAlchemyCloudLinkRepository(sessionmaker, cipher)
    api = cloud_api or HttpxCloudApi(allow_insecure_http=allow_http)
    info = info_provider or SystemInstanceInfoProvider(settings)
    local = telemetry or SqlAlchemyLocalTelemetry(sessionmaker, now)
    pseudonymizers = PseudonymizerProvider(repository)

    sources = [
        TurnSource(sessionmaker, pseudonymizers),
        ConversationSource(sessionmaker, pseudonymizers),
        SessionSource(sessionmaker, pseudonymizers),
        FreeQuerySource(sessionmaker),
    ]
    snapshots = [DatabaseSource(sessionmaker)]
    builder = HeartbeatPayloadBuilder(repository, info, local, now)
    rotate = RotateCredentialsUseCase(repository, api, now=now)

    if sync_lock is None:
        sync_lock = (
            PostgresAdvisorySyncLock(engine)
            if engine is not None and settings.agent_db_engine == "postgresql"
            else NoopSyncLock()
        )

    return CloudLinkServices(
        settings=settings,
        repository=repository,
        cloud_api=api,
        sync_lock=sync_lock,
        link=LinkInstanceUseCase(repository, api, info, allow_insecure_http=allow_http, now=now),
        unlink=UnlinkInstanceUseCase(repository),
        heartbeat=SendHeartbeatUseCase(repository, api, builder, rotate, now=now),
        sync=SyncStreamsUseCase(repository, api, sources, snapshots, now=now),
        rotate=rotate,
        preview=PreviewPayloadUseCase(repository, builder, sources, snapshots, now=now),
    )


_services: CloudLinkServices | None = None


def init_cloud_link_services(services: CloudLinkServices) -> CloudLinkServices:
    global _services
    _services = services
    return services


def get_cloud_link_services() -> CloudLinkServices:
    if _services is None:
        raise RuntimeError("init_cloud_link_services() no se llamó en el lifespan.")
    return _services


def reset_cloud_link_services() -> None:
    global _services
    _services = None
