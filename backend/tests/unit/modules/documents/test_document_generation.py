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


async def test_a_report_can_carry_a_bar_chart_from_the_data(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    from pypdf import PdfReader

    conversation_id = await _conversation(sm)
    table_id = await _saved_table(sm, conversation_id)
    use_case = BuildDocumentUseCase(
        SqlAlchemyResultSetRepository(sm), SqlAlchemyStoredFileRepository(sm), FileRenderer()
    )
    chart = {
        "tipo": "grafico",
        "conjunto": str(table_id),
        "etiqueta": "Producto",
        "valor": "dias_sin_venta",
        "titulo": "Días sin venta por producto",
    }

    pdf = await use_case.execute(
        conversation_id, DocumentSpec.model_validate(_spec(table_id, bloques=[chart])), Branding()
    )
    word = await use_case.execute(
        conversation_id,
        DocumentSpec.model_validate(_spec(table_id, formato="docx", bloques=[chart])),
        Branding(),
    )

    assert len(PdfReader(io.BytesIO(pdf.content)).pages[0].images) == 1
    with zipfile.ZipFile(io.BytesIO(word.content)) as package:
        assert any(n.startswith("word/media/") for n in package.namelist())

    not_numeric = dict(chart, valor="producto")
    with pytest.raises(FileRequestError, match="no es numérica"):
        await use_case.execute(
            conversation_id,
            DocumentSpec.model_validate(_spec(table_id, bloques=[not_numeric])),
            Branding(),
        )


def test_the_chart_draws_the_top_values_in_order() -> None:
    from PIL import Image

    from app.modules.documents.infrastructure.charts import MAX_BARS, bar_chart_png

    items = [(f"Producto {i}", float(i)) for i in range(30)]
    png = bar_chart_png("Prueba", items)

    with Image.open(io.BytesIO(png)) as image:
        assert image.format == "PNG"
        # Alto proporcional a las barras dibujadas: como mucho MAX_BARS, más la
        # línea que avisa cuántas quedaron por fuera.
        assert image.size[1] <= 90 + 34 + 46 * MAX_BARS + 40


async def _numbers_table(
    sm: async_sessionmaker[AsyncSession], conversation_id: UUID, values: list[float]
) -> UUID:
    table = build_result_set(
        conversation_id=conversation_id,
        title="Ventas por mes",
        keys=["mes", "total"],
        labels={"mes": "Mes", "total": "Total"},
        raw_rows=[{"mes": f"Mes {i + 1}", "total": value} for i, value in enumerate(values)],
        has_personal_data=False,
    )
    await SqlAlchemyResultSetRepository(sm).add(table)
    return table.id


def _chart_spec(table_id: UUID, forma: str) -> DocumentSpec:
    chart = {
        "tipo": "grafico",
        "conjunto": str(table_id),
        "etiqueta": "mes",
        "valor": "total",
        "forma": forma,
    }
    return DocumentSpec.model_validate(_spec(table_id, bloques=[chart]))


@pytest.mark.parametrize("forma", ["barras", "torta", "lineas"])
async def test_each_chart_shape_lands_in_the_pdf(
    sm: async_sessionmaker[AsyncSession], forma: str
) -> None:
    from pypdf import PdfReader

    conversation_id = await _conversation(sm)
    table_id = await _numbers_table(sm, conversation_id, [120.0, 80.5, 0.0, 300.0, 45.0])
    use_case = BuildDocumentUseCase(
        SqlAlchemyResultSetRepository(sm), SqlAlchemyStoredFileRepository(sm), FileRenderer()
    )

    pdf = await use_case.execute(conversation_id, _chart_spec(table_id, forma), Branding())

    assert len(PdfReader(io.BytesIO(pdf.content)).pages[0].images) == 1


async def test_a_pie_refuses_negative_values(sm: async_sessionmaker[AsyncSession]) -> None:
    conversation_id = await _conversation(sm)
    table_id = await _numbers_table(sm, conversation_id, [120.0, -30.0, 50.0])
    use_case = BuildDocumentUseCase(
        SqlAlchemyResultSetRepository(sm), SqlAlchemyStoredFileRepository(sm), FileRenderer()
    )

    with pytest.raises(FileRequestError, match="negativos"):
        await use_case.execute(conversation_id, _chart_spec(table_id, "torta"), Branding())
    # Las barras sí los muestran.
    await use_case.execute(conversation_id, _chart_spec(table_id, "barras"), Branding())


async def test_a_line_asks_to_group_when_there_are_too_many_points(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    from app.modules.documents.domain.document import MAX_LINE_POINTS

    conversation_id = await _conversation(sm)
    table_id = await _numbers_table(sm, conversation_id, [1.0] * (MAX_LINE_POINTS + 1))
    use_case = BuildDocumentUseCase(
        SqlAlchemyResultSetRepository(sm), SqlAlchemyStoredFileRepository(sm), FileRenderer()
    )

    with pytest.raises(FileRequestError, match="agrupa la consulta por mes"):
        await use_case.execute(conversation_id, _chart_spec(table_id, "lineas"), Branding())


def test_pie_slices_fold_the_rest_into_others_and_keep_the_total() -> None:
    from app.modules.documents.infrastructure.charts import MAX_SLICES, pie_slices

    items = [(f"Vendedor {i}", float(i)) for i in range(1, 13)]

    slices = pie_slices(items)

    assert len(slices) == MAX_SLICES + 1
    assert slices[0] == ("Vendedor 12", 12.0)
    assert slices[-1] == ("Otros (5)", 1.0 + 2.0 + 3.0 + 4.0 + 5.0)
    assert sum(v for _, v in slices) == sum(v for _, v in items)


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        (0.0, 230.0, [0.0, 100.0, 200.0, 300.0]),
        (0.0, 905_871_472.0, [0.0, 2.5e8, 5e8, 7.5e8, 1e9]),
        (-40.0, 90.0, [-50.0, 0.0, 50.0, 100.0]),
        (0.0, 0.0, [0.0, 0.25, 0.5, 0.75, 1.0]),
    ],
)
def test_line_axis_ticks_are_round_and_cover_the_range(
    low: float, high: float, expected: list[float]
) -> None:
    from app.modules.documents.infrastructure.charts import nice_ticks

    assert nice_ticks(low, high) == pytest.approx(expected)


def test_period_dates_show_as_month_or_year() -> None:
    from app.modules.documents.infrastructure.exporters import date_style, display_value

    def column(values: list[str]) -> Any:
        table = build_result_set(
            conversation_id=uuid4(),
            title="Periodos",
            keys=["fecha"],
            labels={"fecha": "Fecha"},
            raw_rows=[{"fecha": v} for v in values],
            has_personal_data=False,
        )
        return date_style(table, 0)

    assert column(["2025-11-01T00:00:00-05:00", "2025-12-01T00:00:00-05:00"]) == "month"
    assert column(["2025-01-01", "2026-01-01"]) == "year"
    assert column(["2025-11-01", "2025-11-14"]) == "day"
    assert display_value("2025-11-01T00:00:00-05:00", "date", "month") == "nov 2025"
    assert display_value("2026-01-01", "date", "year") == "2026"
    assert display_value("2025-11-14", "date") == "14/11/2025"


def test_pie_slices_leave_out_zeros_and_do_not_fold_a_single_extra() -> None:
    from app.modules.documents.infrastructure.charts import MAX_SLICES, pie_slices

    items = [(f"P{i}", float(i)) for i in range(1, MAX_SLICES + 2)] + [("Cero", 0.0)]

    slices = pie_slices(items)

    # Una sola porción de más se muestra con su nombre: "Otros (1)" no aporta.
    assert len(slices) == MAX_SLICES + 1
    assert all(not label.startswith("Otros") for label, _ in slices)
    assert ("Cero", 0.0) not in slices
