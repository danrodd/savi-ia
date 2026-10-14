"""Identidad de la instalación y telemetría local para el heartbeat."""

from __future__ import annotations

import base64
import hashlib
import logging
import platform
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app._version import __commit__, __version__
from app.infrastructure.config import Settings
from app.modules.auth.infrastructure.persistence.models import RefreshTokenModel
from app.modules.cloud_link.domain.interfaces import (
    InstanceInfo,
    InstanceInfoProvider,
    LlmTelemetry,
    LocalTelemetry,
    TelemetrySnapshot,
)
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel
from app.modules.llm_providers.infrastructure.persistence.models import LlmProviderConfigModel

logger = logging.getLogger(__name__)

_PROCESS_STARTED_AT = datetime.now(UTC)
_LOCAL_SESSION = "local_session"


def _machine_id() -> str:
    """Identificador estable del equipo, o un sustituto si no se puede leer."""
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
                return str(value)
        for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            path = Path(candidate)
            if path.is_file():
                return path.read_text(encoding="utf-8").strip()
    except (OSError, ImportError):
        logger.debug("No se pudo leer el identificador del equipo.", exc_info=True)
    return f"{platform.node()}-{uuid.getnode()}"


class SystemInstanceInfoProvider(InstanceInfoProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def describe(self, install_id: UUID) -> InstanceInfo:
        digest = hashlib.sha256(f"{_machine_id()}{install_id}".encode()).digest()
        fingerprint = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        # La app de escritorio usa SQLite; el servidor, Postgres.
        mode = "desktop" if self._settings.agent_db_engine == "sqlite" else "server"
        return InstanceInfo(
            name=(platform.node() or "SAVI")[:200],
            deployment_mode=mode,
            version=__version__[:64],
            commit=__commit__[:64] if __commit__ else None,
            os=f"{platform.system()} {platform.release()} {platform.version()}"[:200],
            agent_db_engine=self._settings.agent_db_engine,
            fingerprint=fingerprint,
            started_at=_PROCESS_STARTED_AT,
        )


class SqlAlchemyLocalTelemetry(LocalTelemetry):
    """Conteos locales sin contenido: ni nombres, ni textos, ni credenciales."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        now: Callable[[], datetime],
    ) -> None:
        self._sessionmaker = sessionmaker
        self._now = now

    async def collect(self) -> TelemetrySnapshot:
        async with self._sessionmaker() as session:
            llm = await self._llm(session)
            databases = (
                await session.execute(
                    select(
                        ErpDatabaseModel.is_active,
                        ErpDatabaseModel.credentials_unreadable,
                    ).where(ErpDatabaseModel.deleted_at.is_(None))
                )
            ).all()
            sessions = (
                await session.execute(
                    select(func.count())
                    .select_from(RefreshTokenModel)
                    .where(
                        RefreshTokenModel.revoked_at.is_(None),
                        RefreshTokenModel.expires_at > self._now(),
                    )
                )
            ).scalar_one()

        unreadable = sum(1 for d in databases if d.credentials_unreadable)
        usable = sum(1 for d in databases if d.is_active and not d.credentials_unreadable)
        warnings: list[str] = []
        if llm.usable is not True:
            warnings.append("llm_unusable")
        if unreadable:
            warnings.append("credentials_unreadable")
        return TelemetrySnapshot(
            llm=llm,
            databases_total=len(databases),
            databases_usable=usable,
            databases_unreadable=unreadable,
            active_sessions=int(sessions),
            warnings=warnings,
            # TLS lo termina un proxy o el propio servicio: desde el proceso no
            # se puede afirmar, y un `false` inventado generaría alarmas falsas.
            tls=None,
        )

    @staticmethod
    async def _llm(session: AsyncSession) -> LlmTelemetry:
        row = (
            await session.execute(
                select(LlmProviderConfigModel).where(LlmProviderConfigModel.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if row is None:
            return LlmTelemetry(usable=False)
        has_models = bool(row.chat_model) and bool(row.title_model)
        has_credential = row.credential_kind == _LOCAL_SESSION or (
            bool(row.credential_encrypted) and not row.credentials_unreadable
        )
        return LlmTelemetry(
            provider=row.provider[:64],
            model=row.chat_model[:128],
            credential_kind=row.credential_kind[:64],
            usable=has_models and has_credential,
        )
