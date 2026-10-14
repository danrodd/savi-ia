from __future__ import annotations

import base64
import logging
import secrets
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.cloud_link.domain.entities import CloudLinkState, CloudNotice, StreamWatermark
from app.modules.cloud_link.domain.interfaces import CloudLinkRepository
from app.modules.cloud_link.domain.value_objects import (
    AccessRules,
    AiLimits,
    LinkStatus,
    SyncPolicy,
)
from app.modules.cloud_link.infrastructure.persistence.models import (
    CloudLinkModel,
    CloudSyncWatermarkModel,
)
from app.shared.security.credential_cipher import CredentialCipher, CredentialDecryptError

logger = logging.getLogger(__name__)

_SINGLETON_ID = 1
_KEY_BYTES = 32


def _new_key() -> bytes:
    return secrets.token_bytes(_KEY_BYTES)


def _policy_to_json(policy: SyncPolicy | None) -> dict[str, Any] | None:
    if policy is None:
        return None
    return {
        "heartbeat_seconds": policy.heartbeat_seconds,
        "ingest_seconds": policy.ingest_seconds,
        "max_batch_events": policy.max_batch_events,
        "sync_enabled": policy.sync_enabled,
        "config_locked": policy.config_locked,
        "allow_local_cli": policy.allow_local_cli,
        "ai": _ai_to_json(policy.ai),
        "access": _access_to_json(policy.access),
        "identity_mode": policy.identity_mode,
    }


def _ai_to_json(ai: AiLimits | None) -> dict[str, Any] | None:
    if ai is None:
        return None
    return {
        "allowed_providers": sorted(ai.allowed_providers)
        if ai.allowed_providers is not None
        else None,
        "user_monthly_usd": str(ai.user_monthly_usd) if ai.user_monthly_usd is not None else None,
        "provider_monthly_usd": {k: str(v) for k, v in ai.provider_monthly_usd.items()},
        "user_overrides": {k: str(v) for k, v in ai.user_overrides.items()},
    }


def _access_to_json(access: AccessRules | None) -> dict[str, Any] | None:
    if access is None:
        return None
    return {
        "default_databases": sorted(str(d) for d in access.default_databases)
        if access.default_databases is not None
        else None,
        "user_databases": {
            k: sorted(str(d) for d in v) for k, v in access.user_databases.items()
        },
    }


def _uuids(values: Any) -> frozenset[UUID]:
    found: set[UUID] = set()
    if isinstance(values, list):
        for value in cast("list[Any]", values):
            try:
                found.add(UUID(str(value)))
            except ValueError:
                continue  # un identificador ilegible simplemente no autoriza esa base
    return frozenset(found)


def _access_from_json(raw: object) -> AccessRules | None:
    """Tolerante: un identificador ilegible no autoriza nada; nunca amplía el acceso."""
    if not isinstance(raw, dict):
        return None
    data = cast("dict[str, Any]", raw)
    default = data.get("default_databases")
    users = data.get("user_databases")
    return AccessRules(
        default_databases=_uuids(default) if isinstance(default, list) else None,
        user_databases={
            str(k): _uuids(v) for k, v in cast("dict[Any, Any]", users).items()
        }
        if isinstance(users, dict)
        else {},
    )


def _amount(value: object) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def _ai_from_json(raw: object) -> AiLimits | None:
    """Tolerante: lo que no se entiende se descarta; nada inválido bloquea ni habilita de más."""
    if not isinstance(raw, dict):
        return None
    data = cast("dict[str, Any]", raw)
    providers = data.get("allowed_providers")
    per_provider = data.get("provider_monthly_usd")
    overrides = data.get("user_overrides")
    monthly = data.get("user_monthly_usd")
    return AiLimits(
        allowed_providers=(
            frozenset(str(p) for p in cast("list[Any]", providers))
            if isinstance(providers, list)
            else None
        ),
        user_monthly_usd=_amount(monthly) if monthly is not None else None,
        provider_monthly_usd={
            str(k): a
            for k, v in cast("dict[Any, Any]", per_provider).items()
            if (a := _amount(v)) is not None
        }
        if isinstance(per_provider, dict)
        else {},
        user_overrides={
            str(k): a
            for k, v in cast("dict[Any, Any]", overrides).items()
            if (a := _amount(v)) is not None
        }
        if isinstance(overrides, dict)
        else {},
    )


def _policy_from_json(raw: dict[str, Any] | None) -> SyncPolicy | None:
    if not raw:
        return None
    defaults = SyncPolicy()

    def _int(name: str, default: int) -> int:
        value = raw.get(name)
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    enabled = raw.get("sync_enabled")
    locked = raw.get("config_locked")
    local_cli = raw.get("allow_local_cli")
    identity = raw.get("identity_mode")
    return SyncPolicy(
        heartbeat_seconds=_int("heartbeat_seconds", defaults.heartbeat_seconds),
        ingest_seconds=_int("ingest_seconds", defaults.ingest_seconds),
        max_batch_events=_int("max_batch_events", defaults.max_batch_events),
        sync_enabled=enabled if isinstance(enabled, bool) else defaults.sync_enabled,
        config_locked=locked if isinstance(locked, bool) else defaults.config_locked,
        ai=_ai_from_json(raw.get("ai")),
        access=_access_from_json(raw.get("access")),
        allow_local_cli=(
            local_cli if isinstance(local_cli, bool) else defaults.allow_local_cli
        ),
        identity_mode=identity if identity in ("pseudonym", "named") else defaults.identity_mode,
    )


def _status(raw: str) -> LinkStatus:
    try:
        return LinkStatus(raw)
    except ValueError:
        return LinkStatus.UNLINKED


class SqlAlchemyCloudLinkRepository(CloudLinkRepository):
    """Cada operación abre su propia sesión: la usan el scheduler (fuera de
    todo request) y las rutas de administración."""

    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], cipher: CredentialCipher
    ) -> None:
        self._sessionmaker = sessionmaker
        self._cipher = cipher

    # ── estado ───────────────────────────────────────────────────────────

    async def get(self) -> CloudLinkState:
        async with self._sessionmaker() as session:
            model = await self._load_or_create(session)
            state = self._to_entity(model)
            # Si la clave de seudónimos hubo que regenerarla, se persiste ya:
            # leerla otra vez no puede dar una clave distinta.
            if session.dirty:
                await session.commit()
            return state

    async def update(self, mutate: Callable[[CloudLinkState], None]) -> CloudLinkState:
        async with self._sessionmaker() as session:
            model = await self._load_or_create(session, for_update=True)
            state = self._to_entity(model)
            mutate(state)
            self._apply(model, state)
            await session.commit()
            return state

    async def _load_or_create(
        self, session: AsyncSession, *, for_update: bool = False
    ) -> CloudLinkModel:
        statement = select(CloudLinkModel).where(CloudLinkModel.id == _SINGLETON_ID)
        if for_update:
            statement = statement.with_for_update()
        model = (await session.execute(statement)).scalar_one_or_none()
        if model is None:
            model = CloudLinkModel(
                id=_SINGLETON_ID,
                cloud_url="",
                pseudonym_key_encrypted=self._cipher.encrypt(
                    base64.b64encode(_new_key()).decode("ascii")
                ),
                install_id=uuid4(),
                status=LinkStatus.UNLINKED.value,
                notices=[],
                consecutive_failures=0,
            )
            session.add(model)
            try:
                await session.commit()
            except IntegrityError:
                # Otra tarea la creó en el mismo instante.
                await session.rollback()
                model = (await session.execute(statement)).scalar_one()
        return model

    def _to_entity(self, model: CloudLinkModel) -> CloudLinkState:
        try:
            key = base64.b64decode(self._cipher.decrypt(model.pseudonym_key_encrypted))
        except (CredentialDecryptError, ValueError):
            # La clave de cifrado de la instalación cambió: los seudónimos
            # anteriores no se pueden reproducir. Se genera una nueva en lugar
            # de dejar la sincronización muerta, y queda en el log.
            logger.warning(
                "No se pudo leer la clave de seudónimos de SAVI Cloud; se generó una nueva."
            )
            key = _new_key()
            model.pseudonym_key_encrypted = self._cipher.encrypt(
                base64.b64encode(key).decode("ascii")
            )

        secret: str | None = None
        status = _status(model.status)
        last_error = model.last_error_code
        if model.secret_encrypted:
            try:
                secret = self._cipher.decrypt(model.secret_encrypted)
            except CredentialDecryptError:
                logger.warning(
                    "No se pudo leer el secreto de SAVI Cloud: hay que volver a vincular."
                )
                status = LinkStatus.UNAUTHORIZED
                last_error = "credentials_unreadable"

        return CloudLinkState(
            cloud_url=model.cloud_url,
            install_id=model.install_id,
            pseudonym_key=key,
            status=status,
            instance_id=model.instance_id,
            client_code=model.client_code,
            client_name=model.client_name,
            secret=secret,
            policy=_policy_from_json(model.policy),
            notices=[
                CloudNotice(
                    code=str(n.get("code", "")),
                    severity=str(n.get("severity", "info")),
                    message=str(n.get("message", "")),
                )
                for n in (model.notices or [])
            ],
            linked_at=model.linked_at,
            last_heartbeat_ok_at=model.last_heartbeat_ok_at,
            last_attempt_at=model.last_attempt_at,
            secret_rotated_at=model.secret_rotated_at,
            last_error_code=last_error,
            consecutive_failures=model.consecutive_failures,
        )

    def _apply(self, model: CloudLinkModel, state: CloudLinkState) -> None:
        model.cloud_url = state.cloud_url
        model.instance_id = state.instance_id
        model.client_code = state.client_code
        model.client_name = state.client_name
        model.secret_encrypted = (
            self._cipher.encrypt(state.secret) if state.secret is not None else None
        )
        model.pseudonym_key_encrypted = self._cipher.encrypt(
            base64.b64encode(state.pseudonym_key).decode("ascii")
        )
        model.install_id = state.install_id
        model.status = state.status.value
        model.policy = _policy_to_json(state.policy)
        model.notices = [
            {"code": n.code, "severity": n.severity, "message": n.message} for n in state.notices
        ]
        model.linked_at = state.linked_at
        model.last_heartbeat_ok_at = state.last_heartbeat_ok_at
        model.last_attempt_at = state.last_attempt_at
        model.secret_rotated_at = state.secret_rotated_at
        model.last_error_code = state.last_error_code
        model.consecutive_failures = state.consecutive_failures

    # ── marcas ───────────────────────────────────────────────────────────

    async def get_watermark(self, stream: str) -> StreamWatermark | None:
        async with self._sessionmaker() as session:
            model = await session.get(CloudSyncWatermarkModel, stream)
            return self._watermark(model) if model is not None else None

    async def list_watermarks(self) -> list[StreamWatermark]:
        async with self._sessionmaker() as session:
            rows = (await session.execute(select(CloudSyncWatermarkModel))).scalars().all()
            return [self._watermark(r) for r in rows]

    async def save_watermark(self, watermark: StreamWatermark) -> None:
        async with self._sessionmaker() as session:
            model = await session.get(CloudSyncWatermarkModel, watermark.stream)
            if model is None:
                session.add(
                    CloudSyncWatermarkModel(
                        stream=watermark.stream,
                        watermark_at=watermark.at,
                        watermark_id=watermark.id,
                        last_ok_at=watermark.last_ok_at,
                    )
                )
            else:
                model.watermark_at = watermark.at
                model.watermark_id = watermark.id
                model.last_ok_at = watermark.last_ok_at
            await session.commit()

    async def reset_watermarks(self, streams: list[str], at: datetime) -> None:
        async with self._sessionmaker() as session:
            await session.execute(delete(CloudSyncWatermarkModel))
            for stream in streams:
                session.add(
                    CloudSyncWatermarkModel(
                        stream=stream, watermark_at=at, watermark_id="", last_ok_at=None
                    )
                )
            await session.commit()

    async def delete_watermarks(self) -> None:
        async with self._sessionmaker() as session:
            await session.execute(delete(CloudSyncWatermarkModel))
            await session.commit()

    @staticmethod
    def _watermark(model: CloudSyncWatermarkModel) -> StreamWatermark:
        return StreamWatermark(
            stream=model.stream,
            at=model.watermark_at,
            id=model.watermark_id,
            last_ok_at=model.last_ok_at,
        )


__all__ = ["SqlAlchemyCloudLinkRepository"]
