from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from uuid import UUID

from app.modules.chat.domain.entities import ChatEvent


class LLMRunner(ABC):
    @abstractmethod
    def stream_turn(
        self,
        prompt: str,
        *,
        conversation_id: UUID | None = None,
    ) -> AsyncIterator[ChatEvent]: ...
