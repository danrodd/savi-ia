"""Pipeline de procesamiento: extraer → fragmentar → vectorizar.

Todo es trabajo de CPU (pypdf, tokenización, ONNX). Corre en un
`ThreadPoolExecutor` **dedicado** de un solo hilo: nunca en el executor por
defecto del loop, que comparten otras tareas, para que un PDF grande no
encole nada ajeno y el chat siga respondiendo mientras se procesa (RNF-02).
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.modules.company_knowledge.domain.entities.processing import (
    ExtractedText,
    PendingChunk,
)
from app.modules.company_knowledge.domain.exceptions import (
    DocumentExtractionError,
    UnsupportedCompanyDocumentMediaTypeError,
)
from app.modules.company_knowledge.domain.interfaces import (
    Chunker,
    DocumentProcessor,
    Embedder,
    ProcessingOutcome,
    TextExtractor,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentStatusCode,
)
from app.modules.company_knowledge.infrastructure.embeddings.vector_codec import (
    vector_to_bytes,
)

# Promedio mínimo de caracteres por página para considerar que un PDF
# tiene capa de texto. Por debajo, casi seguro es escaneado.
_MIN_CHARS_PER_PDF_PAGE = 50
_EMBED_BATCH = 32


class PipelineDocumentProcessor(DocumentProcessor):
    def __init__(
        self,
        *,
        extractor: TextExtractor,
        chunker: Chunker,
        embedder: Embedder,
        executor: ThreadPoolExecutor,
        max_chunks_per_document: int,
    ) -> None:
        self._extractor = extractor
        self._chunker = chunker
        self._embedder = embedder
        self._executor = executor
        self._max_chunks = max_chunks_per_document

    async def process(self, content: bytes, media_type: str) -> ProcessingOutcome:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._process_sync, content, media_type)

    def _process_sync(self, content: bytes, media_type: str) -> ProcessingOutcome:
        try:
            extracted = self._extractor.extract(content, media_type)
        except DocumentExtractionError as exc:
            return ProcessingOutcome.failed(exc.status_code)
        except UnsupportedCompanyDocumentMediaTypeError:
            return ProcessingOutcome.failed(DocumentStatusCode.ENCODING_UNSUPPORTED)

        if _has_no_text(extracted):
            return ProcessingOutcome(
                status=DocumentStatus.NO_TEXT,
                page_count=extracted.page_count,
                char_count=extracted.char_count,
            )

        drafts = self._chunker.chunk(extracted)
        if not drafts:
            return ProcessingOutcome(
                status=DocumentStatus.NO_TEXT,
                page_count=extracted.page_count,
                char_count=extracted.char_count,
            )
        if len(drafts) > self._max_chunks:
            return ProcessingOutcome(
                status=DocumentStatus.FAILED,
                status_code=DocumentStatusCode.TOO_MANY_CHUNKS,
                page_count=extracted.page_count,
                char_count=extracted.char_count,
            )

        # `EmbedderUnavailableError` se propaga a propósito: el documento
        # vuelve a la cola en lugar de quedar `failed` por la instalación.
        chunks: list[PendingChunk] = []
        for start in range(0, len(drafts), _EMBED_BATCH):
            batch = drafts[start : start + _EMBED_BATCH]
            vectors = self._embedder.embed_passages([draft.embed_text for draft in batch])
            chunks.extend(
                PendingChunk(
                    ordinal=draft.ordinal,
                    text=draft.text,
                    embedding=vector_to_bytes(vector),
                    page_from=draft.page_from,
                    page_to=draft.page_to,
                    heading=draft.heading,
                )
                for draft, vector in zip(batch, vectors, strict=True)
            )

        return ProcessingOutcome(
            status=DocumentStatus.READY,
            page_count=extracted.page_count,
            char_count=extracted.char_count,
            embedding_model=self._embedder.model_name,
            chunks=chunks,
        )


def _has_no_text(extracted: ExtractedText) -> bool:
    if extracted.char_count == 0:
        return True
    if extracted.page_count:
        return extracted.char_count / extracted.page_count < _MIN_CHARS_PER_PDF_PAGE
    return False
