"""Citas de documentos dentro de un turno de chat.

La tool asigna una referencia corta (`D1`, `D2`…) a cada fragmento que
entrega. El modelo cita con esa referencia y, al terminar el turno, solo
sobreviven las que existen en el registro: una referencia inventada no se
convierte en fuente (R8 del PRD).
"""

import re
from dataclasses import dataclass, field
from uuid import UUID

from app.modules.company_knowledge.domain.services.document_access_policy import (
    DocumentAccessContext,
)

_REF_PATTERN = re.compile(r"\[D(\d+)\]")


@dataclass(frozen=True, slots=True)
class CitedChunk:
    document_id: UUID
    version: int
    title: str
    ordinal: int
    page_from: int | None
    page_to: int | None


@dataclass(frozen=True, slots=True)
class CitedSource:
    """Una fuente por documento, con todas sus referencias y páginas unidas."""

    ref: str
    refs: tuple[str, ...]
    document_id: UUID
    version: int
    title: str
    pages: str | None


class CitationRegistry:
    """Referencias estables por turno: el mismo fragmento conserva su `ref`."""

    def __init__(self) -> None:
        self._by_ref: dict[str, CitedChunk] = {}
        self._by_key: dict[tuple[UUID, int, int], str] = {}

    def register(self, chunk: CitedChunk) -> str:
        key = (chunk.document_id, chunk.version, chunk.ordinal)
        existing = self._by_key.get(key)
        if existing is not None:
            return existing
        ref = f"D{len(self._by_ref) + 1}"
        self._by_ref[ref] = chunk
        self._by_key[key] = ref
        return ref

    def __len__(self) -> int:
        return len(self._by_ref)

    def build_sources(self, text: str) -> list[CitedSource]:
        """Fuentes citadas en `text`, agrupadas por documento en orden de aparición."""
        order: list[UUID] = []
        grouped: dict[UUID, list[tuple[str, CitedChunk]]] = {}
        for match in _REF_PATTERN.finditer(text):
            ref = f"D{match.group(1)}"
            chunk = self._by_ref.get(ref)
            if chunk is None:
                continue
            entries = grouped.setdefault(chunk.document_id, [])
            if not entries:
                order.append(chunk.document_id)
            if all(existing != ref for existing, _ in entries):
                entries.append((ref, chunk))

        sources: list[CitedSource] = []
        for document_id in order:
            entries = grouped[document_id]
            first = entries[0][1]
            sources.append(
                CitedSource(
                    ref=entries[0][0],
                    refs=tuple(ref for ref, _ in entries),
                    document_id=document_id,
                    version=first.version,
                    title=first.title,
                    pages=format_pages([(c.page_from, c.page_to) for _, c in entries]),
                )
            )
        return sources


def format_pages(ranges: list[tuple[int | None, int | None]]) -> str | None:
    """Une rangos de páginas: `[(3,4), (9,9), (4,5)]` → `"3-5, 9"`."""
    pages: set[int] = set()
    for start, end in ranges:
        if start is None:
            continue
        pages.update(range(start, (end if end is not None else start) + 1))
    if not pages:
        return None
    ordered = sorted(pages)
    parts: list[str] = []
    run_start = previous = ordered[0]
    for page in ordered[1:]:
        if page == previous + 1:
            previous = page
            continue
        parts.append(_range(run_start, previous))
        run_start = previous = page
    parts.append(_range(run_start, previous))
    return ", ".join(parts)


def _range(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


@dataclass(slots=True)
class TurnDocumentContext:
    """Todo lo que un turno necesita para buscar y citar documentos."""

    access: DocumentAccessContext
    citations: CitationRegistry = field(default_factory=CitationRegistry)
