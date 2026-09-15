from abc import ABC, abstractmethod

from app.modules.company_knowledge.domain.entities.processing import ExtractedText


class TextExtractor(ABC):
    """Extrae texto plano de bytes según el tipo detectado por contenido."""

    @abstractmethod
    def extract(self, content: bytes, media_type: str) -> ExtractedText: ...


class MediaTypeSniffer(ABC):
    """Detecta el tipo real de un archivo por su contenido."""

    @abstractmethod
    def sniff(self, content: bytes, filename: str) -> str:
        """Devuelve un `media_type` soportado o levanta el error correspondiente."""
