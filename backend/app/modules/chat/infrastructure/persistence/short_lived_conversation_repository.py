"""Repositorio de conversaciones con una transacción por operación.

Existe por una razón concreta y medida: el turno del chat duraba lo que
tardaba el LLM en responder, y el repositorio del request escribía el
mensaje del usuario **sin commitear** hasta que terminaba el stream. En
PostgreSQL eso es inocuo (MVCC), pero la instalación de escritorio corre
sobre SQLite, que admite **un solo escritor por archivo**: esa
transacción abierta se quedaba con el lock de escritura todo el turno y
las tareas paralelas —el auto-título y la auditoría de consultas
libres— se colgaban hasta agotar su timeout y morían.

El patrón es el mismo que ya usan `AssistantMessageWriter` y
`ConversationTitleUpdater`: sessionmaker propio, sesión corta, commit
inmediato. La diferencia es el motivo — aquellos lo hacen para
sobrevivir a la cancelación del cliente, este para no retener el lock.

Se declara en `chat` y no en `conversations` a propósito: el resto de
los endpoints de conversaciones son requests cortos donde la sesión del
request es lo correcto. El único que necesita esto es el turno.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.infrastructure.persistence.repositories import (
    SqlAlchemyConversationRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.conversations.domain.entities import Conversation, Message


class ShortLivedConversationRepository(ConversationRepository):
    """Delega en el repositorio de siempre, una transacción por llamada."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    # Las lecturas también abren su propia sesión. Podrían compartir una,
    # pero mezclar duraciones es justamente lo que causó el problema:
    # una sola regla, sin excepciones que después haya que recordar.
    async def save(self, conversation: Conversation) -> Conversation:
        async with self._sessionmaker() as session:
            result = await SqlAlchemyConversationRepository(session).save(conversation)
            await session.commit()
            return result

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        async with self._sessionmaker() as session:
            return await SqlAlchemyConversationRepository(session).get_by_id(conversation_id)

    async def list_for_user(
        self,
        user_id: int | None,
        *,
        owner_erp_database_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        async with self._sessionmaker() as session:
            return await SqlAlchemyConversationRepository(session).list_for_user(
                user_id,
                owner_erp_database_id=owner_erp_database_id,
                limit=limit,
                offset=offset,
            )

    async def update_title(
        self,
        conversation_id: UUID,
        new_title: str,
        *,
        respect_lock: bool = True,
        lock: bool = False,
    ) -> str | None:
        async with self._sessionmaker() as session:
            result = await SqlAlchemyConversationRepository(session).update_title(
                conversation_id, new_title, respect_lock=respect_lock, lock=lock
            )
            await session.commit()
            return result

    async def soft_delete(self, conversation_id: UUID) -> bool:
        async with self._sessionmaker() as session:
            result = await SqlAlchemyConversationRepository(session).soft_delete(conversation_id)
            await session.commit()
            return result

    async def add_message(self, message: Message) -> Message:
        async with self._sessionmaker() as session:
            result = await SqlAlchemyConversationRepository(session).add_message(message)
            await session.commit()
            return result

    async def list_messages(
        self,
        conversation_id: UUID,
        *,
        include_superseded: bool = False,
    ) -> list[Message]:
        async with self._sessionmaker() as session:
            return await SqlAlchemyConversationRepository(session).list_messages(
                conversation_id, include_superseded=include_superseded
            )

    async def get_last_active_message(self, conversation_id: UUID) -> Message | None:
        async with self._sessionmaker() as session:
            return await SqlAlchemyConversationRepository(session).get_last_active_message(
                conversation_id
            )

    async def supersede_messages(
        self,
        message_ids: list[UUID],
        *,
        superseded_by_id: UUID | None = None,
    ) -> None:
        async with self._sessionmaker() as session:
            await SqlAlchemyConversationRepository(session).supersede_messages(
                message_ids, superseded_by_id=superseded_by_id
            )
            await session.commit()
