"""Implementación de `ConversationTitleUpdater` con sesión independiente.

Genera el título con `title_generator.generate_title` (Haiku) y lo
persiste vía un `SqlAlchemyConversationRepository` armado sobre una
sesión nueva del sessionmaker. La sesión se cierra dentro del método,
así la persistencia sobrevive a la cancelación del request.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.config import Settings
from app.modules.chat.domain.interfaces import ConversationTitleUpdater
from app.modules.chat.infrastructure.llm.title_generator import generate_title
from app.modules.conversations.infrastructure.persistence.repositories import (
    SqlAlchemyConversationRepository,
)

log = logging.getLogger(__name__)


class SqlAlchemyConversationTitleUpdater(ConversationTitleUpdater):
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._settings = settings

    async def update_from_user(
        self,
        conversation_id: UUID,
        user_msg: str,
    ) -> str | None:
        return await self._generate_and_persist(
            conversation_id, user_msg, assistant_msg=""
        )

    async def update_from_turn(
        self,
        conversation_id: UUID,
        user_msg: str,
        assistant_msg: str,
    ) -> str | None:
        return await self._generate_and_persist(
            conversation_id, user_msg, assistant_msg=assistant_msg
        )

    async def _generate_and_persist(
        self,
        conversation_id: UUID,
        user_msg: str,
        *,
        assistant_msg: str,
    ) -> str | None:
        title = await generate_title(self._settings, user_msg, assistant_msg)
        if title is None:
            return None
        async with self._sessionmaker() as session:
            repo = SqlAlchemyConversationRepository(session)
            applied = await repo.update_title(
                conversation_id,
                title,
                respect_lock=True,
                lock=False,
            )
            await session.commit()
        if applied is None:
            log.info(
                "title_update_skipped_locked conversation_id=%s",
                conversation_id,
            )
        return applied
