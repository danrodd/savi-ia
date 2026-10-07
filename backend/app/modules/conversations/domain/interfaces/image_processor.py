from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    content: bytes
    mime: str
    width: int
    height: int


class ImageProcessor(ABC):
    @abstractmethod
    def process(self, raw: bytes, *, max_side_px: int) -> ProcessedImage:
        """Valida por contenido, corrige la orientación, reduce y re-codifica.

        Levanta `InvalidChatAttachmentError` si `raw` no es una imagen admitida.
        Es síncrono y pesado en CPU: el caso de uso lo corre en un hilo."""
