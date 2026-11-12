"""Documentos que entrega SAVI (P3 de los hallazgos de la primera demo).

- La especificación del modelo se valida: sin bloques desconocidos, sin HTML
  como formato, sin imágenes ni enlaces.
- Las tablas solo pueden ser de la misma conversación.
- El logo de la empresa sale del ERP, validado y recomprimido.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.conversations.infrastructure.persistence.models.conversation_model import (
    ConversationModel,
)
from app.modules.documents.application.document_spec import DocumentSpec
from app.modules.documents.application.file_use_cases import (
    BuildDocumentUseCase,
    DownloadFileUseCase,
    ExportToFileUseCase,
    FileRequestError,
)
from app.modules.documents.application.use_cases import Owner
from app.modules.documents.domain.document import Branding
from app.modules.documents.domain.files import FileFormat
from app.modules.documents.domain.result_set import build_result_set
from app.modules.documents.infrastructure.branding import normalize_logo
from app.modules.documents.infrastructure.exporters import FileRenderer
from app.modules.documents.infrastructure.repository import (
    SqlAlchemyResultSetRepository,
    SqlAlchemyStoredFileRepository,
)
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel
from app.shared.exceptions import NotFoundError

_DB = UUID("22222222-2222-2222-2222-222222222222")


def _png(size: tuple[int, int] = (900, 300)) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", size, (185, 28, 28)).save(out, format="PNG")
    return out.getvalue()


@pytest_asyncio.fixture
async def sm(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'g.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as s:
        s.add(
            ErpDatabaseModel(
                id=_DB,
                code="DB",
                name="DB",
                host="h",
                port=5432,
                database="db",
                username="u",
                password_encrypted="x",
            )
        )
        await s.commit()
    yield factory
    await engine.dispose()


async def _conversation(sm: async_sessionmaker[AsyncSession], user_id: int = 7) -> UUID:
    conversation_id = uuid4()
    async with sm() as s:
        s.add(
            ConversationModel(
                id=conversation_id,
                user_id=user_id,
                title="Inventario",
                erp_database_id=_DB,
                owner_erp_database_id=_DB,
            )
        )
        await s.commit()
    return conversation_id


async def _saved_table(sm: async_sessionmaker[AsyncSession], conversation_id: UUID) -> UUID:
    table = build_result_set(
        conversation_id=conversation_id,
        title="Llantas sin movimiento",
        keys=["codigo", "producto", "dias_sin_venta"],
        labels={"codigo": "Código", "producto": "Producto", "dias_sin_venta": "Días sin venta"},
        raw_rows=[
            {
                "codigo": "LLANTAS0354",
                "producto": "265/60R18 MICHELIN FORCE LTX",
                "dias_sin_venta": 509,
            },
            {"codigo": "LLANTAS0306", "producto": "215/70R16 TERRAMAX", "dias_sin_venta": 1318},
        ],
        has_personal_data=False,
    )
    await SqlAlchemyResultSetRepository(sm).add(table)
    return table.id


def _spec(table_id: UUID, **over: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "formato": "pdf",
        "titulo": "Informe de llantas sin movimiento",
        "bloques": [
            {"tipo": "parrafo", "texto": "Hay **2 referencias** con más de un año sin venta."},
            {"tipo": "datos_clave", "items": [["Referencias", "2"]]},
            {"tipo": "tabla", "conjunto": str(table_id), "columnas": ["codigo", "producto"]},
            {"tipo": "lista", "items": ["Revisar el DOT"]},
        ],
    }
    spec.update(over)
    return spec


# ── Especificación ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    [
        {"bloques": [{"tipo": "imagen", "url": "http://malo.example/x.png"}]},
        {"bloques": [{"tipo": "parrafo", "texto": "hola", "html": "<script>"}]},
        {"formato": "html"},
        {"bloques": []},
        {"bloques": [{"tipo": "tabla", "conjunto": "no-es-un-id"}]},
    ],
)
def test_an_invalid_spec_is_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DocumentSpec.model_validate(_spec(uuid4(), **bad))


# ── Casos de uso ─────────────────────────────────────────────────────────


async def test_a_report_is_built_with_the_rows_and_the_company_logo(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    conversation_id = await _conversation(sm)
    table_id = await _saved_table(sm, conversation_id)
    files = SqlAlchemyStoredFileRepository(sm)
    branding = Branding(name="IMPORLLANTAS DEL HUILA", logo_png=normalize_logo(_png()))

    stored = await BuildDocumentUseCase(
        SqlAlchemyResultSetRepository(sm), files, FileRenderer()
    ).execute(
        conversation_id, DocumentSpec.model_validate(_spec(table_id, formato="docx")), branding
    )

    assert stored.filename == "Informe de llantas sin movimiento.docx"
    with zipfile.ZipFile(io.BytesIO(stored.content)) as package:
        body = package.read("word/document.xml").decode()
        media = [n for n in package.namelist() if n.startswith("word/media/")]
    assert "MICHELIN FORCE LTX" in body and "IMPORLLANTAS DEL HUILA" in body
    assert media, "el logo tiene que ir en el documento"

    downloaded = await DownloadFileUseCase(files).execute(stored.id, Owner(7, _DB))
    assert downloaded.content == stored.content
    with pytest.raises(NotFoundError):
        await DownloadFileUseCase(files).execute(stored.id, Owner(8, _DB))


async def test_a_table_from_another_conversation_is_refused(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    mine = await _conversation(sm)
    other = await _conversation(sm, user_id=9)
    foreign_table = await _saved_table(sm, other)

    with pytest.raises(FileRequestError, match="no existe en esta conversación"):
        await BuildDocumentUseCase(
            SqlAlchemyResultSetRepository(sm), SqlAlchemyStoredFileRepository(sm), FileRenderer()
        ).execute(mine, DocumentSpec.model_validate(_spec(foreign_table)), Branding())


async def test_export_without_an_id_uses_the_latest_query_of_the_conversation(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    conversation_id = await _conversation(sm)
    await _saved_table(sm, conversation_id)

    stored = await ExportToFileUseCase(
        SqlAlchemyResultSetRepository(sm), SqlAlchemyStoredFileRepository(sm), FileRenderer()
    ).execute(conversation_id, FileFormat.PDF, None, Branding(name="IMPORLLANTAS"))

    assert stored.content.startswith(b"%PDF")
    assert stored.filename == "Llantas sin movimiento.pdf"


async def test_export_without_data_tells_the_model_to_query_first(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    conversation_id = await _conversation(sm)

    with pytest.raises(FileRequestError, match="Primero"):
        await ExportToFileUseCase(
            SqlAlchemyResultSetRepository(sm), SqlAlchemyStoredFileRepository(sm), FileRenderer()
        ).execute(conversation_id, FileFormat.XLSX, None, Branding())


# ── Logo ─────────────────────────────────────────────────────────────────


def test_the_logo_is_validated_shrunk_and_reencoded() -> None:
    from PIL import Image

    logo = normalize_logo(_png((2000, 1000)))

    assert logo is not None
    with Image.open(io.BytesIO(logo)) as image:
        assert image.format == "PNG"
        assert max(image.size) <= 400


@pytest.mark.parametrize("raw", [b"", b"no es una imagen", b"\x89PNG\r\n\x1a\nroto"])
def test_a_broken_logo_is_dropped(raw: bytes) -> None:
    assert normalize_logo(raw) is None


async def test_columns_are_matched_by_label_and_unknown_ones_are_explained(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    # Así falló en la prueba real: el modelo pidió las columnas por su etiqueta.
    conversation_id = await _conversation(sm)
    table_id = await _saved_table(sm, conversation_id)
    use_case = BuildDocumentUseCase(
        SqlAlchemyResultSetRepository(sm), SqlAlchemyStoredFileRepository(sm), FileRenderer()
    )
    by_label = _spec(table_id)
    by_label["bloques"][2]["columnas"] = ["Código", "PRODUCTO"]

    stored = await use_case.execute(
        conversation_id, DocumentSpec.model_validate(by_label), Branding()
    )
    assert stored.content.startswith(b"%PDF")

    unknown = _spec(table_id)
    unknown["bloques"][2]["columnas"] = ["bodega"]
    with pytest.raises(FileRequestError, match="Usa algunas de: codigo, producto, dias_sin_venta"):
        await use_case.execute(conversation_id, DocumentSpec.model_validate(unknown), Branding())
