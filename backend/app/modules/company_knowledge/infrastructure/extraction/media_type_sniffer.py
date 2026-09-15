from pathlib import Path

from app.modules.company_knowledge.domain.exceptions import (
    UnsupportedCompanyDocumentMediaTypeError,
)
from app.modules.company_knowledge.domain.interfaces.text_extractor import MediaTypeSniffer
from app.modules.company_knowledge.infrastructure.extraction.media_types import (
    MARKDOWN_EXTENSIONS,
    MARKDOWN_MEDIA_TYPE,
    PDF_MEDIA_TYPE,
    TEXT_MEDIA_TYPE,
)

_PDF_MAGIC = b"%PDF-"
_UTF8_BOMS = (b"\xef\xbb\xbf",)
_CP1252_CONTROL_CHARS = frozenset(
    chr(code) for code in range(0x00, 0x20) if code not in (0x09, 0x0A, 0x0D)
)


def decode_text(content: bytes) -> str | None:
    """Decodifica UTF-8 (con o sin BOM) o `cp1252` sin controles.

    Devuelve `None` si no es texto razonable.
    """
    raw = content
    for bom in _UTF8_BOMS:
        if raw.startswith(bom):
            raw = raw[len(bom) :]
            break
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        candidate = content.decode("cp1252")
    except UnicodeDecodeError:
        return None
    if any(ch in _CP1252_CONTROL_CHARS for ch in candidate):
        return None
    return candidate


class ContentMediaTypeSniffer(MediaTypeSniffer):
    """Detecta el tipo real por contenido; nunca confía en la extensión."""

    def sniff(self, content: bytes, filename: str) -> str:
        if content.startswith(_PDF_MAGIC):
            return PDF_MEDIA_TYPE
        text = decode_text(content)
        if text is None:
            raise UnsupportedCompanyDocumentMediaTypeError()
        suffix = Path(filename).suffix.lower()
        if suffix in MARKDOWN_EXTENSIONS:
            return MARKDOWN_MEDIA_TYPE
        return TEXT_MEDIA_TYPE
