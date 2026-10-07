from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.chat.domain.entities import ChatEvent, ImageInput
from app.modules.company_knowledge.domain.services import TurnDocumentContext


class LLMRunner(ABC):
    @abstractmethod
    def stream_turn(
        self,
        prompt: str,
        *,
        conversation_id: UUID | None = None,
        allowed_modules: frozenset[ModuleCode] | None = None,
        erp_database_id: UUID | None = None,
        document_context: TurnDocumentContext | None = None,
        images: Sequence[ImageInput] = (),
    ) -> AsyncIterator[ChatEvent]: ...
