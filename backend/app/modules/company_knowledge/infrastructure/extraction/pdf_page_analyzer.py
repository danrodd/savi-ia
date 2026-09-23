"""Análisis local del PDF por página y armado de tramos, con `pypdf`.

Es gratis y tarda milisegundos por página. Da el texto de respaldo, las
métricas que deciden el modo mixto (Fase 5) y los tramos que se mandan a la
IA. No decodifica imágenes: el tamaño sale de `/Width` y `/Height` del
XObject.
"""

from collections.abc import Sequence
from io import BytesIO
from typing import Any, cast

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject

from app.modules.company_knowledge.domain.entities.page_reading import (
    PageMetrics,
    PdfAnalysis,
)
from app.modules.company_knowledge.domain.exceptions import DocumentExtractionError
from app.modules.company_knowledge.domain.interfaces import PdfPageAnalyzer
from app.modules.company_knowledge.domain.value_objects import DocumentStatusCode
from app.modules.company_knowledge.infrastructure.extraction.media_types import (
    PDF_MEDIA_TYPE,
)
from app.modules.company_knowledge.infrastructure.extraction.pdf_extractor import (
    PdfTextExtractor,
)

# Formularios anidados dentro de formularios: los PDF de escáner no pasan
# de uno o dos niveles; el tope evita recorrer un ciclo mal armado.
_MAX_XOBJECT_DEPTH = 3


class PypdfPageAnalyzer(PdfPageAnalyzer):
    def __init__(self, max_pages: int) -> None:
        self._text = PdfTextExtractor(max_pages)

    def analyze(self, content: bytes) -> PdfAnalysis:
        # Cifrado, ilegible y máximo de páginas: mismas reglas y códigos que
        # la extracción de texto de siempre.
        extracted = self._text.extract(content, PDF_MEDIA_TYPE)
        reader = _open(content)
        pages: list[PageMetrics] = []
        for index, text in enumerate(extracted.pages):
            count, largest = _image_stats(reader, index)
            pages.append(
                PageMetrics(
                    page_number=index + 1,
                    text=text,
                    image_count=count,
                    max_image_pixels=largest,
                )
            )
        return PdfAnalysis(pages=pages)

    def measure_pages(self, content: bytes, page_numbers: Sequence[int]) -> dict[int, int]:
        # Un solo `PdfReader` para todo: abrir el PDF por página era
        # cuadrático con escaneos de 60 MB.
        reader = _open(content)
        return {number: len(_write(reader, [number])) for number in page_numbers}

    def build_segments(self, content: bytes, groups: Sequence[Sequence[int]]) -> list[bytes]:
        reader = _open(content)
        return [_write(reader, group) for group in groups]


def _write(reader: PdfReader, page_numbers: Sequence[int]) -> bytes:
    writer = PdfWriter()
    for number in page_numbers:
        writer.add_page(reader.pages[number - 1])
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _open(content: bytes) -> PdfReader:
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            reader.decrypt("")
        return reader
    except Exception as exc:  # noqa: BLE001
        raise DocumentExtractionError(
            DocumentStatusCode.PDF_UNREADABLE, "No pudimos leer el PDF."
        ) from exc


def _image_stats(reader: PdfReader, index: int) -> tuple[int, int]:
    """Cantidad de imágenes de la página y píxeles de la más grande.

    Una página rota no invalida el documento: se informa como sin imágenes.
    """
    try:
        resources = reader.pages[index].get("/Resources")
        return _walk_xobjects(resources, 0)
    except Exception:  # noqa: BLE001
        return 0, 0


def _walk_xobjects(resources: Any, depth: int) -> tuple[int, int]:
    if depth > _MAX_XOBJECT_DEPTH or resources is None:
        return 0, 0
    resources = resources.get_object()
    if not isinstance(resources, DictionaryObject):
        return 0, 0
    xobjects = resources.get("/XObject")
    if xobjects is None:
        return 0, 0
    xobjects = xobjects.get_object()
    if not isinstance(xobjects, DictionaryObject):
        return 0, 0
    count = 0
    largest = 0
    for ref in xobjects.values():
        xobject = cast(DictionaryObject, ref.get_object())
        subtype = xobject.get("/Subtype")
        if subtype == "/Image":
            count += 1
            width = int(cast(int, xobject.get("/Width", 0)))
            height = int(cast(int, xobject.get("/Height", 0)))
            largest = max(largest, width * height)
        elif subtype == "/Form":
            nested_count, nested_largest = _walk_xobjects(xobject.get("/Resources"), depth + 1)
            count += nested_count
            largest = max(largest, nested_largest)
    return count, largest
