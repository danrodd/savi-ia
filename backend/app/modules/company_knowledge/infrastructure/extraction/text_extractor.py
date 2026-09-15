from app.modules.company_knowledge.domain.entities.processing import ExtractedText
from app.modules.company_knowledge.domain.exceptions import (
    UnsupportedCompanyDocumentMediaTypeError,
)
from app.modules.company_knowledge.domain.interfaces import TextExtractor
from app.modules.company_knowledge.infrastructure.extraction.media_type_sniffer import (
    decode_text,
)
from app.modules.company_knowledge.infrastructure.extraction.media_types import (
    PDF_MEDIA_TYPE,
)
from app.modules.company_knowledge.infrastructure.extraction.pdf_extractor import (
    PdfTextExtractor,
    normalize_text,
)


class DispatchTextExtractor(TextExtractor):
    """Ruta la extracción según el `media_type` detectado por contenido."""

    def __init__(self, max_pages: int) -> None:
        self._pdf = PdfTextExtractor(max_pages)

    def extract(self, content: bytes, media_type: str) -> ExtractedText:
        if media_type == PDF_MEDIA_TYPE:
            return self._pdf.extract(content, media_type)
        decoded = decode_text(content)
        if decoded is None:
            raise UnsupportedCompanyDocumentMediaTypeError()
        return ExtractedText(
            pages=[normalize_text(decoded)],
            media_type=media_type,
            page_count=None,
        )
