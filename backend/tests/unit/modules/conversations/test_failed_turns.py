"""Turnos fallidos para el administrador: solo los de su base, los más nuevos primero."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.conversations.application.use_cases.list_failed_turns import (
    ListFailedTurnsUseCase,
)
from app.modules.conversations.infrastructure.persistence.models.conversation_model import (
    ConversationModel,
    MessageModel,
)
from app.modules.conversations.infrastructure.persistence.repositories.sqlalchemy_failed_turn_reader import (  # noqa: E501
    SqlAlchemyFailedTurnReader,
)
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel

_MINE = UUID("22222222-2222-2222-2222-222222222222")
_OTHER = UUID("33333333-3333-3333-3333-333333333333")


@pytest_asyncio.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'f.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as s:
        for db, code in ((_MINE, "MIA"), (_OTHER, "OTRA")):
            s.add(
                ErpDatabaseModel(
                    id=db,
                    code=code,
                    name=code,
                    host="h",
                    port=5432,
                    database=code,
                    username="u",
                    password_encrypted="x",
                )
            )
        await s.commit()
        yield s
    await engine.dispose()


def _conversation(s: AsyncSession, db: UUID, title: str) -> UUID:
    conversation_id = uuid4()
    s.add(
        ConversationModel(
            id=conversation_id,
            user_id=7,
            title=title,
            erp_database_id=db,
            owner_erp_database_id=db,
        )
    )
    return conversation_id


def _message(
    s: AsyncSession, conversation_id: UUID, finish: str, minutes_ago: int, code: str | None
) -> None:
    s.add(
        MessageModel(
            id=uuid4(),
            conversation_id=conversation_id,
            role="assistant",
            content="",
            finish_reason=finish,
            tool_invocations=[
                {"id": "t1", "name": "consultar_datos", "input": {}, "status": "ok"},
                {"id": "t2", "name": "consultar_conocimiento", "input": {}, "status": "ok"},
            ],
            error_code="provider_busy" if finish == "error" else None,
            support_code=code,
            provider="openai",
            model="gpt-6-luna",
            created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )
    )


async def test_only_failed_turns_of_the_admin_database_newest_first(session: AsyncSession) -> None:
    mine = _conversation(session, _MINE, "Inventario")
    other = _conversation(session, _OTHER, "Ajena")
    await session.flush()
    _message(session, mine, "error", 30, "OLD00001")
    _message(session, mine, "error", 5, "NEW00002")
    _message(session, mine, "complete", 1, None)
    _message(session, other, "error", 2, "AJENA003")
    await session.commit()

    turns = await ListFailedTurnsUseCase(SqlAlchemyFailedTurnReader(session)).execute(_MINE)

    assert [t.support_code for t in turns] == ["NEW00002", "OLD00001"]
    assert turns[0].conversation_title == "Inventario"
    assert turns[0].erp_queries == 1
    assert turns[0].error_code == "provider_busy"
