from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.chat.domain.interfaces import AssistantMessageWriter
from app.modules.conversations.domain.entities import Message
from app.modules.conversations.infrastructure.persistence.mappers import (
    ConversationOrmMapper,
)


class SqlAlchemyAssistantMessageWriter(AssistantMessageWriter):
    """Implementación con sessionmaker independiente del request.

    Abre una sesión nueva en cada `write()` y la cierra inmediatamente.
    Esto permite que la persistencia se ejecute como `asyncio.create_task`
    fuera del lifecycle del request — sobrevive a la cancelación del
    cliente.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def write(self, message: Message) -> None:
        async with self._sessionmaker() as session:
            model = ConversationOrmMapper.message_to_model(message)
            session.add(model)
            await session.commit()
