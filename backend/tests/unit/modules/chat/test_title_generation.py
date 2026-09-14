"""Auto-título: el updater depende del puerto, no de un proveedor."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.chat.domain.interfaces import TitleGenerator
from app.modules.chat.infrastructure.llm.title_prompt import build_title_prompt, clean_title
from app.modules.chat.infrastructure.persistence.sqlalchemy_conversation_title_updater import (
    SqlAlchemyConversationTitleUpdater,
)
from app.modules.conversations.infrastructure.persistence.models import ConversationModel


class _FixedTitle(TitleGenerator):
    def __init__(self, title: str | None) -> None:
        self.title = title
        self.calls: list[tuple[str, str]] = []

    async def generate(self, user_msg: str, assistant_msg: str = "") -> str | None:
        self.calls.append((user_msg, assistant_msg))
        return self.title


def test_clean_title_strips_quotes_and_final_dot() -> None:
    assert clean_title('  "Facturas pendientes."  ') == "Facturas pendientes"
    assert clean_title("   ") is None


def test_prompt_includes_the_assistant_only_in_phase_two() -> None:
    assert "Asistente:" not in build_title_prompt("hola")
    assert "Asistente: respuesta" in build_title_prompt("hola", "respuesta")


async def test_updater_persists_the_title_from_the_port(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    conversation_id = uuid4()
    async with sessionmaker() as session:
        session.add(ConversationModel(id=conversation_id, title="Nueva conversación"))
        await session.commit()

    generator = _FixedTitle("Estado de cuenta")
    updater = SqlAlchemyConversationTitleUpdater(sessionmaker, generator)

    applied = await updater.update_from_turn(conversation_id, "¿cuánto debo?", "Debes $100")

    assert applied == "Estado de cuenta"
    assert generator.calls == [("¿cuánto debo?", "Debes $100")]
    await engine.dispose()


async def test_updater_does_nothing_when_the_port_returns_none(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}")
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)

    updater = SqlAlchemyConversationTitleUpdater(sessionmaker, _FixedTitle(None))

    assert await updater.update_from_user(uuid4(), "hola") is None
    await engine.dispose()
