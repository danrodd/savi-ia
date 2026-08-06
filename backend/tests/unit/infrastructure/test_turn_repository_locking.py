"""El turno del chat no puede retener el lock de escritura de SQLite.

Reproduce el bug que se veía sólo en la instalación de escritorio: el
repositorio del turno escribía con la sesión del request, que FastAPI
cierra recién al terminar la respuesta — y en un `StreamingResponse` eso
es después de todo el turno. Sobre PostgreSQL (lo que se usa en
desarrollo) es inocuo por MVCC; sobre SQLite, que admite un solo
escritor por archivo, dejaba colgadas al auto-título y a la auditoría
hasta agotar su timeout.

El `timeout` de un segundo es deliberado: si alguien vuelve a introducir
una transacción larga, el test falla en un segundo en vez de tardar los
treinta de producción.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.chat.infrastructure.persistence import ShortLivedConversationRepository
from app.modules.conversations.domain.entities import Conversation, Message, MessageRole

# Los modelos tienen que estar importados para que `create_all` los vea.
from app.modules.conversations.infrastructure.persistence.models import (  # noqa: F401
    ConversationModel,
    MessageModel,
)
from app.modules.conversations.infrastructure.persistence.repositories import (
    SqlAlchemyConversationRepository,
)

_BUSY_TIMEOUT_S = 1.0


@pytest_asyncio.fixture
async def sessionmaker_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    db = tmp_path / "agente.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db.as_posix()}",
        connect_args={"timeout": _BUSY_TIMEOUT_S},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _pragmas(dbapi_connection, _record) -> None:  # noqa: ANN001 - firma del evento
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


async def _other_writer_can_write(
    factory: async_sessionmaker[AsyncSession], conversation_id: str
) -> None:
    """Escribe desde una sesión independiente, como el auto-título."""
    async with factory() as session:
        await SqlAlchemyConversationRepository(session).add_message(
            Message(conversation_id=conversation_id, role=MessageRole.ASSISTANT, content="ok")
        )
        await session.commit()


@pytest.mark.asyncio
async def test_turn_writes_release_the_lock_immediately(
    sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = ShortLivedConversationRepository(sessionmaker_factory)
    conversation = await repository.save(Conversation(title="Prueba"))

    await repository.add_message(
        Message(conversation_id=conversation.id, role=MessageRole.USER, content="hola")
    )

    # Con el repositorio del request esto explotaba con "database is
    # locked": el INSERT de arriba seguía sin commitear.
    await _other_writer_can_write(sessionmaker_factory, conversation.id)

    assert len(await repository.list_messages(conversation.id)) == 2


@pytest.mark.asyncio
async def test_the_test_would_catch_a_long_transaction(
    sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Prueba que el test de arriba puede fallar de verdad.

    Reproduce a mano la transacción larga que había antes: escribe sin
    commitear y deja la sesión abierta, como hacía la del request durante
    el stream. Si esto NO bloqueara, el test de arriba no probaría nada.
    """
    from sqlalchemy.exc import OperationalError

    repository = ShortLivedConversationRepository(sessionmaker_factory)
    conversation = await repository.save(Conversation(title="Prueba"))

    async with sessionmaker_factory() as long_session:
        await SqlAlchemyConversationRepository(long_session).add_message(
            Message(conversation_id=conversation.id, role=MessageRole.USER, content="hola")
        )
        # Sin commit y sin cerrar: es exactamente la sesión del request
        # durante el stream.
        with pytest.raises(OperationalError, match="database is locked"):
            await _other_writer_can_write(sessionmaker_factory, conversation.id)
