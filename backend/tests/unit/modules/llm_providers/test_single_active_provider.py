"""El índice único parcial impide dos proveedores activos a la vez, y
`activate()` baja el anterior en la misma transacción."""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.value_objects import CredentialKind, ProviderKind
from app.modules.llm_providers.infrastructure.persistence import (
    LlmProviderConfigModel,
    SqlAlchemyLlmProviderRepository,
)
from app.shared.security import FernetCredentialCipher


@pytest_asyncio.fixture
async def sessionmaker_(
    tmp_path: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'v.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[LlmProviderConfigModel.__table__]
        )
    yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


def _repo(sm: async_sessionmaker[AsyncSession]) -> SqlAlchemyLlmProviderRepository:
    cipher = FernetCredentialCipher(Fernet.generate_key().decode())
    return SqlAlchemyLlmProviderRepository(sm, cipher)


def _config(provider: ProviderKind, *, is_active: bool = False) -> LlmProviderConfig:
    return LlmProviderConfig(
        provider=provider,
        credential_kind=CredentialKind.API_KEY,
        credential="secret",
        chat_model="model-chat",
        title_model="model-title",
        is_active=is_active,
    )


async def test_activate_deactivates_the_previous_one(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    await repo.save(_config(ProviderKind.CLAUDE, is_active=True))
    await repo.save(_config(ProviderKind.GEMINI))

    await repo.activate(ProviderKind.GEMINI)

    claude = await repo.get(ProviderKind.CLAUDE)
    gemini = await repo.get(ProviderKind.GEMINI)
    assert claude is not None and claude.is_active is False
    assert gemini is not None and gemini.is_active is True


async def test_get_active_returns_none_without_any_active(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    await repo.save(_config(ProviderKind.CLAUDE))

    assert await repo.get_active() is None
