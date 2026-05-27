from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.chat.domain.interfaces import AssistantMessageWriter
from app.modules.conversations.domain.entities import Message
from app.modules.conversations.infrastructure.persistence.mappers import (
    ConversationOrmMapper,
)
from app.modules.conversations.infrastructure.persistence.models import MessageModel


class SqlAlchemyAssistantMessageWriter(AssistantMessageWriter):
    """Implementación con sessionmaker independiente del request.

    Abre una sesión nueva en cada `write()` y la cierra inmediatamente.
    Esto permite que la persistencia se ejecute como `asyncio.create_task`
    fuera del lifecycle del request — sobrevive a la cancelación del
    cliente.

    Si `supersedes_id` se pasa, hace el enlace ↔ con el mensaje viejo
    en la misma transacción.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def write(
        self,
        message: Message,
        *,
        supersedes_id: UUID | None = None,
    ) -> None:
        async with self._sessionmaker() as session:
            model = ConversationOrmMapper.message_to_model(message)
            session.add(model)
            await session.flush()
            if supersedes_id is not None:
                await session.execute(
                    update(MessageModel)
                    .where(MessageModel.id == supersedes_id)
                    .values(superseded_by_id=message.id)
                )
            await session.commit()
