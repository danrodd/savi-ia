from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExtractedText:
    """Resultado de extraer texto de un archivo.

    `pages` conserva el texto por página en PDF; en TXT/Markdown tiene un
    único elemento con todo el contenido. `page_count` es `None` en texto
    plano y la cantidad real de páginas en PDF.
    """

    pages: list[str]
    media_type: str
    page_count: int | None = None

    @property
    def char_count(self) -> int:
        return sum(len(page) for page in self.pages)


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    """Fragmento antes de vectorizar.

    `text` es lo que se persiste y se muestra; `embed_text` incluye el
    encabezado vigente para que aporte contexto al embedding.
    """

    ordinal: int
    text: str
    embed_text: str
    page_from: int | None = None
    page_to: int | None = None
    heading: str | None = None


@dataclass(frozen=True, slots=True)
class PendingChunk:
    """Fragmento listo para persistir, con su vector serializado."""

    ordinal: int
    text: str
    embedding: bytes
    page_from: int | None = None
    page_to: int | None = None
    heading: str | None = None
