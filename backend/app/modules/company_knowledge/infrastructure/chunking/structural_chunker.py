import re
from dataclasses import dataclass

from app.modules.company_knowledge.domain.entities.processing import (
    ChunkDraft,
    ExtractedText,
)
from app.modules.company_knowledge.domain.interfaces import Chunker
from app.modules.company_knowledge.infrastructure.extraction.media_types import (
    MARKDOWN_MEDIA_TYPE,
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_UPPERCASE_HEADING_MAX = 80
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass(frozen=True, slots=True)
class _Block:
    text: str
    page_from: int | None
    page_to: int | None
    heading: str | None


class StructuralChunker(Chunker):
    """Divide en bloques estructurales y los agrupa con solapamiento."""

    def __init__(self, chunk_tokens: int, overlap_tokens: int) -> None:
        self._chunk_tokens = max(1, chunk_tokens)
        self._overlap_tokens = max(0, overlap_tokens)

    def chunk(self, extracted: ExtractedText) -> list[ChunkDraft]:
        blocks = self._build_blocks(extracted)
        if not blocks:
            return []

        chunks: list[ChunkDraft] = []
        current: list[_Block] = []
        current_tokens = 0
        tail = ""

        def flush() -> None:
            nonlocal current, current_tokens, tail
            if not current:
                return
            raw_text = "\n\n".join(block.text for block in current).strip()
            heading = current[0].heading
            page_from = min((b.page_from for b in current if b.page_from is not None), default=None)
            page_to = max((b.page_to for b in current if b.page_to is not None), default=None)
            text = f"{tail}\n\n{raw_text}" if tail else raw_text
            embed_text = f"{heading}\n{text}" if heading else text
            chunks.append(
                ChunkDraft(
                    ordinal=len(chunks),
                    text=text,
                    embed_text=embed_text,
                    page_from=page_from,
                    page_to=page_to,
                    heading=heading,
                )
            )
            tail = self._tail(raw_text)
            current = []
            current_tokens = 0

        for block in blocks:
            block_tokens = _estimate_tokens(block.text)
            if block_tokens > self._chunk_tokens:
                flush()
                for piece in self._split_oversized(block):
                    piece_tokens = _estimate_tokens(piece.text)
                    if current and current_tokens + piece_tokens > self._chunk_tokens:
                        flush()
                    current.append(piece)
                    current_tokens += piece_tokens
                    if current_tokens >= self._chunk_tokens:
                        flush()
                continue
            if current and current_tokens + block_tokens > self._chunk_tokens:
                flush()
            current.append(block)
            current_tokens += block_tokens

        flush()
        return chunks

    def _build_blocks(self, extracted: ExtractedText) -> list[_Block]:
        if extracted.page_count is None:
            source = extracted.pages[0] if extracted.pages else ""
            if extracted.media_type == MARKDOWN_MEDIA_TYPE:
                return self._markdown_blocks(source)
            return self._paragraph_blocks(source, None, None)

        blocks: list[_Block] = []
        for index, page in enumerate(extracted.pages):
            page_number = index + 1
            blocks.extend(self._paragraph_blocks(page, page_number, page_number))
        return blocks

    def _paragraph_blocks(
        self, text: str, page_from: int | None, page_to: int | None
    ) -> list[_Block]:
        blocks: list[_Block] = []
        for paragraph in _PARAGRAPH_SPLIT.split(text):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            blocks.append(
                _Block(
                    text=paragraph,
                    page_from=page_from,
                    page_to=page_to,
                    heading=self._infer_heading(paragraph),
                )
            )
        return blocks

    def _markdown_blocks(self, text: str) -> list[_Block]:
        blocks: list[_Block] = []
        heading: str | None = None
        buffer: list[str] = []

        def flush_buffer() -> None:
            if not buffer:
                return
            content = "\n".join(buffer).strip()
            if content:
                blocks.append(_Block(content, None, None, heading))
            buffer.clear()

        for line in text.split("\n"):
            match = _HEADING_RE.match(line)
            if match:
                flush_buffer()
                heading = match.group(2).strip()
                continue
            if not line.strip():
                flush_buffer()
                continue
            buffer.append(line)
        flush_buffer()
        return blocks

    @staticmethod
    def _infer_heading(paragraph: str) -> str | None:
        first_line = paragraph.split("\n", 1)[0].strip()
        if not first_line or len(first_line) > _UPPERCASE_HEADING_MAX:
            return None
        if first_line.endswith("."):
            return None
        letters = [ch for ch in first_line if ch.isalpha()]
        if letters and all(ch.isupper() for ch in letters):
            return first_line
        return None

    def _split_oversized(self, block: _Block) -> list[_Block]:
        pieces: list[_Block] = []
        buffer = ""
        for sentence in _SENTENCE_SPLIT.split(block.text):
            candidate = f"{buffer} {sentence}".strip() if buffer else sentence
            if buffer and _estimate_tokens(candidate) > self._chunk_tokens:
                pieces.append(_Block(buffer, block.page_from, block.page_to, block.heading))
                buffer = sentence
            else:
                buffer = candidate
        if buffer:
            pieces.append(_Block(buffer, block.page_from, block.page_to, block.heading))
        return pieces

    def _tail(self, text: str) -> str:
        if self._overlap_tokens <= 0:
            return ""
        chars = self._overlap_tokens * _CHARS_PER_TOKEN
        if len(text) <= chars:
            return ""
        snippet = text[-chars:]
        boundary = snippet.find(" ")
        if boundary != -1:
            snippet = snippet[boundary + 1 :]
        return snippet.strip()
