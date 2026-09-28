"""Fixtures del módulo `company_knowledge`.

- `sessionmaker_`: SQLite temporal real con las tablas del módulo, porque
  parte de lo verificado ES el motor (transacciones, índice único parcial,
  escrituras condicionales).
- `HashingEmbedder`: embedder determinístico sin modelo ONNX. Vectoriza por
  hashing de tokens: textos que comparten palabras quedan cerca. Alcanza
  para probar el pipeline y el índice sin descargar nada.
- `make_pdf`: PDF mínimo válido con capa de texto, escrito a mano.
- `make_scanned_pdf`: PDF de páginas que son solo una imagen, sin capa de
  texto: lo que produce un escáner o una app de fotos del celular.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
)
from app.modules.company_knowledge.domain.exceptions import EmbedderUnavailableError
from app.modules.company_knowledge.domain.interfaces import Embedder
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentVisibility,
)
from app.modules.company_knowledge.infrastructure.index.tokenizer import tokenize
from app.modules.company_knowledge.infrastructure.persistence.models import (
    CompanyDocumentAiReadModel,
    CompanyDocumentBlobModel,
    CompanyDocumentChunkModel,
    CompanyDocumentDatabaseModel,
    CompanyDocumentModel,
    CompanyDocumentPageModel,
    CompanyKnowledgeSettingsModel,
    CompanyWebPageModel,
    CompanyWebSourceDatabaseModel,
    CompanyWebSourceModel,
)
from app.modules.conversations.infrastructure.persistence.models import (
    ConversationModel,
    MessageModel,
)
from app.modules.erp_databases.infrastructure.persistence import ErpDatabaseModel

DIM = 64


@pytest_asyncio.fixture
async def sessionmaker_(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'docs.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                ErpDatabaseModel.__table__,
                ConversationModel.__table__,
                MessageModel.__table__,
                CompanyDocumentModel.__table__,
                CompanyDocumentDatabaseModel.__table__,
                CompanyDocumentBlobModel.__table__,
                CompanyDocumentChunkModel.__table__,
                CompanyDocumentPageModel.__table__,
                CompanyDocumentAiReadModel.__table__,
                CompanyKnowledgeSettingsModel.__table__,
                CompanyWebSourceModel.__table__,
                CompanyWebSourceDatabaseModel.__table__,
                CompanyWebPageModel.__table__,
            ],
        )
    yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


class HashingEmbedder(Embedder):
    def __init__(self, *, model_name: str = "test-hashing", available: bool = True) -> None:
        self._model_name = model_name
        self.available = available
        self.calls = 0

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return DIM

    def is_available(self) -> bool:
        return self.available

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        if not self.available:
            raise EmbedderUnavailableError()
        self.calls += 1
        vector = np.zeros(DIM, dtype=np.float32)
        for token in tokenize(text):
            bucket = int(hashlib.sha256(token.encode()).hexdigest(), 16) % DIM
            vector[bucket] += 1.0
        norm = float(np.linalg.norm(vector))
        return (vector / norm if norm else vector).tolist()


def make_pdf(pages: Sequence[str]) -> bytes:
    """PDF 1.4 mínimo, una línea de texto Helvetica por página."""
    objects: list[bytes] = []
    page_ids = [3 + 2 * i for i in range(len(pages))]
    font_id = 3 + 2 * len(pages)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for index, text in enumerate(pages):
        content_id = page_ids[index] + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


def make_scanned_pdf(page_count: int, *, width: int = 40, height: int = 60) -> bytes:
    """PDF 1.4 con una imagen gris por página y ninguna capa de texto."""
    objects: list[bytes] = []
    page_ids = [3 + 3 * i for i in range(page_count)]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode())
    pixels = bytes([180]) * (width * height)
    for page_id in page_ids:
        content_id, image_id = page_id + 1, page_id + 2
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /XObject << /Im1 {image_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode()
        )
        stream = b"q 612 0 0 792 0 0 cm /Im1 Do Q"
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
        objects.append(
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
            f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Length {len(pixels)} >>".encode()
            + b"\nstream\n"
            + pixels
            + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


def make_document(
    *,
    title: str = "Manual de caja",
    visibility: DocumentVisibility = DocumentVisibility.ALL,
    modules: Sequence[ModuleCode] = (),
    all_databases: bool = True,
    database_ids: Sequence[UUID] = (),
    status: DocumentStatus = DocumentStatus.PENDING,
    media_type: str = "text/markdown",
    sha256: str | None = None,
) -> CompanyDocument:
    return CompanyDocument(
        title=title,
        original_filename=f"{title}.md",
        media_type=media_type,
        size_bytes=10,
        sha256=sha256 or uuid4().hex + uuid4().hex,
        status=status,
        visibility=visibility,
        modules=list(modules),
        all_databases=all_databases,
        database_ids=list(database_ids),
        uploaded_by_login="ADMIN",
        uploaded_by_database_id=uuid4(),
        uploaded_by_user_id=1,
    )
