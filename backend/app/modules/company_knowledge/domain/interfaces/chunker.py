from abc import ABC, abstractmethod

from app.modules.company_knowledge.domain.entities.processing import (
    ChunkDraft,
    ExtractedText,
)


class Chunker(ABC):
    """Divide texto extraído en fragmentos estructurales con solapamiento."""

    @abstractmethod
    def chunk(self, extracted: ExtractedText) -> list[ChunkDraft]: ...
