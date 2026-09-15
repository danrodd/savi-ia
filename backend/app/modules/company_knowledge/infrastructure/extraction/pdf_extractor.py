import re
from collections import Counter
from io import BytesIO

from pypdf import PdfReader

from app.modules.company_knowledge.domain.entities.processing import ExtractedText
from app.modules.company_knowledge.domain.exceptions import DocumentExtractionError
from app.modules.company_knowledge.domain.value_objects import DocumentStatusCode
from app.modules.company_knowledge.infrastructure.extraction.media_types import (
    PDF_MEDIA_TYPE,
)

_HYPHEN_BREAK = re.compile(r"(\w)-\n([^\W\d_])", re.UNICODE)
_CONTROL_BLANKS = re.compile(r"[ \t]+\n")
_MANY_BLANKS = re.compile(r"\n{3,}")
_REPEATED_PAGE_RATIO = 0.6
_MAX_REPEATED_LINE_LEN = 200


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = _CONTROL_BLANKS.sub("\n", text)
    text = _MANY_BLANKS.sub("\n\n", text)
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _remove_repeated_lines(pages: list[str]) -> list[str]:
    if len(pages) < 3:
        return pages
    occurrences: Counter[str] = Counter()
    for page in pages:
        seen = {
            line.strip()
            for line in page.split("\n")
            if line.strip() and len(line.strip()) <= _MAX_REPEATED_LINE_LEN
        }
        occurrences.update(seen)
    threshold = _REPEATED_PAGE_RATIO * len(pages)
    repeated = {line for line, count in occurrences.items() if count >= threshold}
    if not repeated:
        return pages
    cleaned: list[str] = []
    for page in pages:
        kept = [line for line in page.split("\n") if line.strip() not in repeated]
        cleaned.append("\n".join(kept).strip())
    return cleaned


class PdfTextExtractor:
    """Extrae texto de un PDF con `pypdf` (Python puro)."""

    def __init__(self, max_pages: int) -> None:
        self._max_pages = max_pages

    def extract(self, content: bytes, media_type: str) -> ExtractedText:
        try:
            reader = PdfReader(BytesIO(content))
        except Exception as exc:  # noqa: BLE001
            raise DocumentExtractionError(
                DocumentStatusCode.PDF_UNREADABLE, "No pudimos leer el PDF."
            ) from exc

        if reader.is_encrypted:
            try:
                decrypted = reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise DocumentExtractionError(
                    DocumentStatusCode.PDF_ENCRYPTED,
                    "El PDF está cifrado y no pudimos abrirlo.",
                ) from exc
            if not decrypted:
                raise DocumentExtractionError(
                    DocumentStatusCode.PDF_ENCRYPTED,
                    "El PDF está cifrado y requiere contraseña.",
                )

        try:
            page_count = len(reader.pages)
        except Exception as exc:  # noqa: BLE001
            raise DocumentExtractionError(
                DocumentStatusCode.PDF_UNREADABLE, "No pudimos leer el PDF."
            ) from exc

        if page_count > self._max_pages:
            raise DocumentExtractionError(
                DocumentStatusCode.TOO_MANY_PAGES,
                f"El PDF supera el máximo de {self._max_pages} páginas.",
            )

        try:
            raw_pages = [(page.extract_text() or "") for page in reader.pages]
        except Exception as exc:  # noqa: BLE001
            raise DocumentExtractionError(
                DocumentStatusCode.PDF_UNREADABLE, "No pudimos extraer el texto del PDF."
            ) from exc

        pages = [normalize_text(page) for page in raw_pages]
        pages = _remove_repeated_lines(pages)
        return ExtractedText(pages=pages, media_type=PDF_MEDIA_TYPE, page_count=page_count)
