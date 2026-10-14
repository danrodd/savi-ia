"""El listado expone `message_count` (mensajes NO superseded) sin N+1.

La barra lateral oculta las conversaciones vacías: necesita saber de
verdad si una conversación tiene mensajes, no adivinarlo por el título.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.conversations.application.mappers import ConversationMapper
from app.modules.conversations.application.responses.conversation_responses import (
    ConversationResponse,
)
from app.modules.conversations.domain.entities import Conversation
from app.modules.conversations.infrastructure.persistence.models import MessageModel
from app.modules.conversations.infrastructure.persistence.repositories import (
    SqlAlchemyConversationRepository,
)

_USER_ID = 7


@pytest_asyncio.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'mc.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _conversation(repository: SqlAlchemyConversationRepository, title: str) -> UUID:
    saved = await repository.save(Conversation(id=uuid4(), user_id=_USER_ID, title=title))
    return saved.id


def _message(conversation_id: UUID, *, superseded: bool = False) -> MessageModel:
    return MessageModel(
        id=uuid4(),
        conversation_id=conversation_id,
        role="user",
        content="hola",
        superseded_at=datetime(2026, 6, 1, tzinfo=UTC) if superseded else None,
    )


async def test_list_returns_active_message_count_per_conversation(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyConversationRepository(session)
    empty = await _conversation(repository, "Vacía")
    two = await _conversation(repository, "Con dos")
    session.add_all([_message(two), _message(two)])
    await session.commit()

    listed = await repository.list_for_user(_USER_ID)

    counts = {c.id: c.message_count for c in listed}
    assert counts == {empty: 0, two: 2}


async def test_superseded_messages_are_not_counted(session: AsyncSession) -> None:
    repository = SqlAlchemyConversationRepository(session)
    only_superseded = await _conversation(repository, "Solo reemplazados")
    mixed = await _conversation(repository, "Mixta")
    session.add_all(
        [
            _message(only_superseded, superseded=True),
            _message(mixed, superseded=True),
            _message(mixed),
        ]
    )
    await session.commit()

    listed = await repository.list_for_user(_USER_ID)

    counts = {c.id: c.message_count for c in listed}
    assert counts == {only_superseded: 0, mixed: 1}


async def test_count_survives_pagination(session: AsyncSession) -> None:
    repository = SqlAlchemyConversationRepository(session)
    first = await _conversation(repository, "Primera")
    second = await _conversation(repository, "Segunda")
    session.add_all([_message(first), _message(second), _message(second)])
    await session.commit()

    page = await repository.list_for_user(_USER_ID, limit=1)

    assert len(page) == 1
    expected = 1 if page[0].id == first else 2
    assert page[0].message_count == expected


def test_response_exposes_message_count() -> None:
    entity = Conversation(user_id=_USER_ID, message_count=3)

    response = ConversationResponse.from_dto(ConversationMapper.to_dto(entity))

    assert response.message_count == 3
    assert ConversationResponse.model_fields["message_count"].default == 0
