"""Impl `LlmProviderRepository` con sessionmaker independiente.

Es la **frontera del cifrado**: la entidad viaja con la credencial en
claro, la columna la guarda cifrada, y la traducción ocurre acá y solo
acá.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.interfaces import LlmProviderRepository
from app.modules.llm_providers.domain.value_objects import (
    CredentialKind,
    ModelPricing,
    ProviderKind,
)
from app.modules.llm_providers.infrastructure.persistence.models import (
    LlmProviderConfigModel,
)
from app.shared.security import CredentialCipher, CredentialDecryptError

logger = logging.getLogger(__name__)


class SqlAlchemyLlmProviderRepository(LlmProviderRepository):
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        cipher: CredentialCipher,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._cipher = cipher

    # ── Lectura ──────────────────────────────────────────────────────

    async def get(self, provider: ProviderKind) -> LlmProviderConfig | None:
        async with self._sessionmaker() as session:
            stmt = select(LlmProviderConfigModel).where(
                LlmProviderConfigModel.provider == provider.value
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def get_active(self) -> LlmProviderConfig | None:
        async with self._sessionmaker() as session:
            stmt = select(LlmProviderConfigModel).where(
                LlmProviderConfigModel.is_active.is_(True)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def list_all(self) -> list[LlmProviderConfig]:
        async with self._sessionmaker() as session:
            stmt = select(LlmProviderConfigModel).order_by(LlmProviderConfigModel.provider)
            rows = (await session.execute(stmt)).scalars().all()
        return [self._to_entity(r) for r in rows]

    async def count(self) -> int:
        async with self._sessionmaker() as session:
            stmt = select(func.count()).select_from(LlmProviderConfigModel)
            return int((await session.execute(stmt)).scalar_one())

    # ── Escritura ────────────────────────────────────────────────────

    async def save(self, config: LlmProviderConfig) -> None:
        async with self._sessionmaker() as session:
            stmt = select(LlmProviderConfigModel).where(
                LlmProviderConfigModel.provider == config.provider.value
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                row = LlmProviderConfigModel(
                    id=config.id,
                    provider=config.provider.value,
                    is_active=config.is_active,
                )
                session.add(row)
            self._apply(row, config)
            await session.commit()

    async def activate(self, provider: ProviderKind) -> None:
        async with self._sessionmaker() as session:
            # Dos sentencias en la misma transacción, en este orden: el
            # índice único parcial rechazaría tener dos activos a la vez.
            await session.execute(
                update(LlmProviderConfigModel)
                .where(
                    LlmProviderConfigModel.is_active.is_(True),
                    LlmProviderConfigModel.provider != provider.value,
                )
                .values(is_active=False)
            )
            await session.execute(
                update(LlmProviderConfigModel)
                .where(LlmProviderConfigModel.provider == provider.value)
                .values(is_active=True)
            )
            await session.commit()

    # ── Traducción ORM ↔ dominio ─────────────────────────────────────

    def _to_entity(self, row: LlmProviderConfigModel) -> LlmProviderConfig:
        """El descifrado que falla NO se propaga: la entidad vuelve con
        `credentials_unreadable=True` y sin credencial."""
        unreadable = row.credentials_unreadable
        credential: str | None = None
        if row.credential_encrypted and not unreadable:
            try:
                credential = self._cipher.decrypt(row.credential_encrypted)
            except CredentialDecryptError:
                logger.warning(
                    "Credencial ilegible para el proveedor de IA '%s': "
                    "ERP_CREDENTIALS_KEY no coincide. Hay que re-ingresarla "
                    "desde administración.",
                    row.provider,
                )
                unreadable = True

        return LlmProviderConfig(
            id=row.id,
            provider=ProviderKind(row.provider),
            credential_kind=CredentialKind(row.credential_kind),
            credential=credential,
            credentials_unreadable=unreadable,
            chat_model=row.chat_model,
            title_model=row.title_model,
            pricing=_pricing_from_json(row.pricing),
            is_active=row.is_active,
            last_test_ok_at=row.last_test_ok_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _apply(self, row: LlmProviderConfigModel, config: LlmProviderConfig) -> None:
        row.credential_kind = config.credential_kind.value
        row.chat_model = config.chat_model
        row.title_model = config.title_model
        row.pricing = _pricing_to_json(config.pricing)
        row.last_test_ok_at = config.last_test_ok_at
        if config.credential_kind == CredentialKind.LOCAL_SESSION:
            row.credential_encrypted = None
            row.credentials_unreadable = False
        elif config.credential:
            row.credential_encrypted = self._cipher.encrypt(config.credential)
            row.credentials_unreadable = False
        else:
            # Sin credencial en la entidad = conservar la cifrada que ya
            # está (o ninguna si es nueva).
            row.credentials_unreadable = config.credentials_unreadable


def _pricing_to_json(pricing: dict[str, ModelPricing]) -> dict[str, Any]:
    return {
        model: {
            "input": p.input,
            "output": p.output,
            "cache_read": p.cache_read,
            "cache_write": p.cache_write,
        }
        for model, p in pricing.items()
    }


def _pricing_from_json(raw: dict[str, Any] | None) -> dict[str, ModelPricing]:
    result: dict[str, ModelPricing] = {}
    for model, value in (raw or {}).items():
        if not isinstance(value, dict):
            continue
        prices: dict[str, Any] = value  # pyright: ignore[reportUnknownVariableType]
        result[model] = ModelPricing(
            input=float(prices.get("input", 0.0)),
            output=float(prices.get("output", 0.0)),
            cache_read=float(prices.get("cache_read", 0.0)),
            cache_write=float(prices.get("cache_write", 0.0)),
        )
    return result
