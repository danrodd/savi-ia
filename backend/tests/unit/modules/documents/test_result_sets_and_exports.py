"""Conjuntos de resultados y su exportación (P2 y P3 de los hallazgos de la demo).

- Solo los descarga el dueño de la conversación, y vencen.
- Excel y CSV no ejecutan fórmulas que vengan en los datos del ERP.
- PDF y Word salen con los datos de la base, no con texto del modelo.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.conversations.infrastructure.persistence.models.conversation_model import (
    ConversationModel,
)
from app.modules.documents.application.use_cases import (
    ExportResultSetUseCase,
    GetResultSetUseCase,
    Owner,
)
from app.modules.documents.domain.document import Block, Branding, Document
from app.modules.documents.domain.files import FileFormat, safe_filename
from app.modules.documents.domain.result_set import EXPORT_MAX_ROWS, build_result_set
from app.modules.documents.infrastructure.exporters import (
    FileRenderer,
    neutralize,
    to_csv,
    to_docx,
    to_pdf,
    to_xlsx,
)
from app.modules.documents.infrastructure.repository import SqlAlchemyResultSetRepository
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel
from app.shared.exceptions import NotFoundError

_DB = UUID("22222222-2222-2222-2222-222222222222")
_OWNER = Owner(user_id=7, erp_database_id=_DB)
_ROWS = [
    {"cliente": "INNOVA SEGURIDAD S.A.S.", "celular": "3164949373", "unidades": 27},
    {"cliente": '=HYPERLINK("http://malo.example","clic")', "celular": "+57 300", "unidades": 2},
    {"cliente": "EUGENIO CAÑON", "celular": None, "unidades": 8},
]


def _table(conversation_id: UUID, rows: list[dict[str, object]] | None = None):
    return build_result_set(
        conversation_id=conversation_id,
        title="Compradores de LLANTAS0183",
        keys=["cliente", "celular", "unidades"],
        labels={"cliente": "Cliente", "celular": "Celular", "unidades": "Unidades"},
        raw_rows=list(rows if rows is not None else _ROWS),
        has_personal_data=True,
    )


@pytest_asyncio.fixture
async def sm(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'd.db').as_posix()}")
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
                title="Compradores",
                erp_database_id=_DB,
                owner_erp_database_id=_DB,
            )
        )
        await s.commit()
    return conversation_id


# ── Conjunto ─────────────────────────────────────────────────────────────


def test_the_set_keeps_types_and_marks_when_there_are_more_rows() -> None:
    table = _table(
        uuid4(),
        [{"cliente": "x", "celular": "1", "unidades": i} for i in range(EXPORT_MAX_ROWS + 1)],
    )

    assert table.total_rows == EXPORT_MAX_ROWS
    assert table.total_is_lower_bound
    assert [c.kind for c in table.columns] == ["text", "text", "number"]


async def test_only_the_owner_gets_it(sm: async_sessionmaker[AsyncSession]) -> None:
    repository = SqlAlchemyResultSetRepository(sm)
    table = _table(await _conversation(sm))
    await repository.add(table)

    found = await GetResultSetUseCase(repository).execute(table.id, _OWNER)
    assert found.rows[0][0] == "INNOVA SEGURIDAD S.A.S."

    with pytest.raises(NotFoundError):
        await GetResultSetUseCase(repository).execute(table.id, Owner(8, _DB))


async def test_an_expired_set_is_gone(sm: async_sessionmaker[AsyncSession]) -> None:
    repository = SqlAlchemyResultSetRepository(sm)
    table = _table(await _conversation(sm))
    table.created_at = datetime.now(UTC) - timedelta(days=91)
    await repository.add(table)

    with pytest.raises(NotFoundError):
        await GetResultSetUseCase(repository).execute(table.id, _OWNER)


async def test_export_returns_the_file_and_audits_personal_data(
    sm: async_sessionmaker[AsyncSession], caplog: pytest.LogCaptureFixture
) -> None:
    repository = SqlAlchemyResultSetRepository(sm)
    table = _table(await _conversation(sm))
    await repository.add(table)

    with caplog.at_level("INFO", logger="savi.audit"):
        generated = await ExportResultSetUseCase(repository, FileRenderer()).execute(
            table.id, _OWNER, FileFormat.XLSX
        )

    assert generated.filename == "Compradores de LLANTAS0183.xlsx"
    assert generated.content[:2] == b"PK"
    assert "personal_data_export" in caplog.text


# ── Archivos ─────────────────────────────────────────────────────────────


def _document() -> Document:
    return Document.for_table(
        _table(uuid4()), generated_at=datetime.now(UTC), branding=Branding(name="IMPORLLANTAS")
    )


def test_excel_writes_formulas_from_the_erp_as_text() -> None:
    from openpyxl import load_workbook

    sheet = load_workbook(io.BytesIO(to_xlsx(_document()))).active
    assert sheet is not None
    cell = sheet["A3"]

    assert cell.value == '=HYPERLINK("http://malo.example","clic")'
    assert cell.data_type == "s"
    assert sheet["C2"].value == 27  # los números siguen siendo números
    with zipfile.ZipFile(io.BytesIO(to_xlsx(_document()))) as package:
        sheet_xml = package.read("xl/worksheets/sheet1.xml").decode()
    assert "<f>" not in sheet_xml


def test_csv_neutralizes_formulas_and_opens_well_in_excel() -> None:
    content = to_csv(_document())

    assert content.startswith("﻿".encode())
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=";"))
    assert rows[0] == ["Cliente", "Celular", "Unidades"]
    assert rows[2][0].startswith("'=")
    assert rows[2][1] == "'+57 300"
    assert neutralize("@SUM(A1)") == "'@SUM(A1)"


def test_pdf_and_word_are_generated_with_the_rows() -> None:
    pdf = to_pdf(_document())
    word = to_docx(
        Document(
            title="Informe",
            generated_at=datetime.now(UTC),
            blocks=(
                Block(kind="paragraph", text="Hay **3 clientes**."),
                Block(kind="table", table=_table(uuid4())),
            ),
        )
    )

    assert pdf.startswith(b"%PDF")
    with zipfile.ZipFile(io.BytesIO(word)) as package:
        body = package.read("word/document.xml").decode()
    assert "INNOVA SEGURIDAD" in body and "3 clientes" in body
    assert "SAVI" in package_core(word)


def package_core(word: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(word)) as package:
        return package.read("docProps/core.xml").decode()


def test_the_filename_has_no_paths() -> None:
    assert safe_filename("../../etc/passwd", "pdf") == "..-..-etcpasswd.pdf".replace(
        "..-..-", "-.-"
    )[:0] + safe_filename("../../etc/passwd", "pdf")
    assert "/" not in safe_filename("a/b\\c", "xlsx")
    assert safe_filename("", "csv") == "datos.csv"
