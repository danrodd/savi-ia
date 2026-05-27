from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.modules.chat.domain.entities import ChatEvent


class LLMRunner(ABC):
    @abstractmethod
    def stream_turn(self, prompt: str) -> AsyncIterator[ChatEvent]: ...
