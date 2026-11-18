import re
from abc import ABC, abstractmethod
from enum import StrEnum

from app.modules.documents.domain.document import Document


class FileFormat(StrEnum):
    XLSX = "xlsx"
    CSV = "csv"
    PDF = "pdf"
    DOCX = "docx"

    @property
    def media_type(self) -> str:
        return _MEDIA_TYPES[self]


_MEDIA_TYPES = {
    FileFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FileFormat.CSV: "text/csv; charset=utf-8",
    FileFormat.PDF: "application/pdf",
    FileFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Una tabla se exporta en estos; un documento con texto, en PDF o Word.
TABLE_FORMATS = (FileFormat.XLSX, FileFormat.CSV, FileFormat.PDF)
DOCUMENT_FORMATS = (FileFormat.PDF, FileFormat.DOCX)


class DocumentRenderer(ABC):
    @abstractmethod
    def render(self, document: Document, file_format: FileFormat) -> bytes: ...


_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9ÁÉÍÓÚÑáéíóúñ ._-]+")


def safe_filename(title: str, extension: str) -> str:
    """Nombre de archivo sin rutas ni caracteres raros, con la extensión del formato."""
    base = _UNSAFE_FILENAME.sub("", title.replace("/", "-").replace("\\", "-")).strip(" .")
    return f"{base[:80] or 'datos'}.{extension}"
