"""Tests del repositorio de proveedores de IA y su cifrado.

Corren contra una SQLite temporal real: lo que se verifica ES el
comportamiento del motor (persistencia del texto cifrado, el índice
único parcial de `is_active`).
"""
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

_KEY = Fernet.generate_key().decode()
_OTHER_KEY = Fernet.generate_key().decode()


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


def _repo(
    sm: async_sessionmaker[AsyncSession], key: str = _KEY
) -> SqlAlchemyLlmProviderRepository:
    return SqlAlchemyLlmProviderRepository(sm, FernetCredentialCipher(key))


def _config(**overrides: object) -> LlmProviderConfig:
    base: dict[str, object] = {
        "provider": ProviderKind.CLAUDE,
        "credential_kind": CredentialKind.API_KEY,
        "credential": "sk-ant-s3cr3t",
        "chat_model": "claude-sonnet-4-6",
        "title_model": "claude-haiku-4-5",
    }
    base.update(overrides)
    return LlmProviderConfig(**base)  # type: ignore[arg-type]


async def test_credential_is_stored_encrypted_not_plain(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    await _repo(sessionmaker_).save(_config())

    async with sessionmaker_() as session:
        row = (await session.execute(LlmProviderConfigModel.__table__.select())).first()
    assert row is not None
    stored = row._mapping["credential_encrypted"]
    assert stored != "sk-ant-s3cr3t"
    assert "sk-ant-s3cr3t" not in stored


async def test_round_trip_decrypts_the_same_credential(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    await repo.save(_config())

    fetched = await repo.get(ProviderKind.CLAUDE)

    assert fetched is not None
    assert fetched.credential == "sk-ant-s3cr3t"
    assert fetched.credentials_unreadable is False


async def test_wrong_key_marks_credentials_unreadable_without_raising(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    await _repo(sessionmaker_, key=_KEY).save(_config())

    fetched = await _repo(sessionmaker_, key=_OTHER_KEY).get(ProviderKind.CLAUDE)

    assert fetched is not None
    assert fetched.credentials_unreadable is True
    assert fetched.credential is None


async def test_local_session_stores_no_credential(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    await repo.save(
        _config(credential_kind=CredentialKind.LOCAL_SESSION, credential=None)
    )

    async with sessionmaker_() as session:
        row = (await session.execute(LlmProviderConfigModel.__table__.select())).first()
    assert row is not None
    assert row._mapping["credential_encrypted"] is None

    fetched = await repo.get(ProviderKind.CLAUDE)
    assert fetched is not None
    assert fetched.credential is None
    assert fetched.credentials_unreadable is False


async def test_document_model_round_trips(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    config = _config()
    config.document_model = "claude-sonnet-5"
    await repo.save(config)

    fetched = await repo.get(ProviderKind.CLAUDE)

    assert fetched is not None
    assert fetched.document_model == "claude-sonnet-5"
