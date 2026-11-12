"""Generadores de archivos: Excel, CSV, PDF y Word, en Python puro.

Reglas que valen para todos (ver `docs/plataforma/12-generacion-de-documentos.md`):

- Los datos se escriben como datos: una celda del ERP que empieza con `=`, `+`,
  `-`, `@`, tabulador o retorno de carro NO se ejecuta como fórmula.
- Sin macros, sin hipervínculos, sin imágenes remotas.
- Los metadatos (autor, título) los pone el servidor: autor "SAVI".
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from app.modules.documents.domain.document import Document
from app.modules.documents.domain.files import DocumentRenderer, FileFormat
from app.modules.documents.domain.result_set import ResultColumn, ResultSet

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_TZ = ZoneInfo("America/Bogota")
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9 ._-]+")

FOOTER = "Generado por SAVI con datos del ERP"


def neutralize(value: str) -> str:
    """Texto que una hoja de cálculo no interpreta como fórmula."""
    return f"'{value}" if value.startswith(_FORMULA_START) else value


def _selected(table: ResultSet, columns: tuple[str, ...]) -> list[tuple[int, ResultColumn]]:
    indexed = list(enumerate(table.columns))
    if not columns:
        return indexed
    by_key = {c.key: (i, c) for i, c in indexed}
    return [by_key[key] for key in columns if key in by_key]


def _display(value: Any, kind: str) -> str:
    """Texto para PDF y Word: montos con separador de miles, fechas cortas."""
    if value is None:
        return ""
    if kind == "number" and isinstance(value, int | float):
        if float(value).is_integer():
            return f"{int(value):,}".replace(",", ".")
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if kind == "date" and isinstance(value, str):
        try:
            return date.fromisoformat(value[:10]).strftime("%d/%m/%Y")
        except ValueError:
            return value
    return str(value)


def _stamp(document: Document) -> str:
    local = document.generated_at.astimezone(_TZ)
    return f"{FOOTER} el {local.strftime('%d/%m/%Y a las %H:%M')}"


def _total_note(table: ResultSet) -> str:
    if table.total_is_lower_bound:
        return f"Primeras {table.total_rows:,} filas de una consulta más grande.".replace(",", ".")
    return f"{table.total_rows:,} filas.".replace(",", ".")


# ── Excel ────────────────────────────────────────────────────────────────


def to_xlsx(document: Document) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    workbook.remove(workbook.active)  # type: ignore[arg-type]
    workbook.properties.creator = "SAVI"
    workbook.properties.title = document.title[:200]
    tables = [b for b in document.blocks if b.kind == "table" and b.table is not None]
    for number, block in enumerate(tables, start=1):
        table = block.table
        assert table is not None  # noqa: S101 — filtrado arriba
        name = _UNSAFE_FILENAME.sub("", table.title)[:28].strip() or f"Datos {number}"
        sheet = workbook.create_sheet(
            title=f"{name}"[:31] if len(tables) == 1 else f"{number} {name}"[:31]
        )
        selected = _selected(table, block.columns)
        sheet.append([c.label for _, c in selected])
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="B91C1C")
        for row in table.rows:
            values: list[Any] = []
            for index, column in selected:
                value = row[index]
                if column.kind == "date" and isinstance(value, str):
                    try:
                        value = (
                            datetime.fromisoformat(value)
                            if "T" in value
                            else date.fromisoformat(value[:10])
                        )
                        if isinstance(value, datetime) and value.tzinfo is not None:
                            value = value.astimezone(_TZ).replace(tzinfo=None)
                    except ValueError:
                        pass
                values.append(value)
            sheet.append(values)
            # Lo que es texto queda como texto aunque empiece con "=": openpyxl
            # lo marcaría como fórmula y Excel la ejecutaría al abrir.
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        sheet.freeze_panes = "A2"
        if table.rows:
            sheet.auto_filter.ref = sheet.dimensions
        for position, (index, column) in enumerate(selected, start=1):
            longest = max(
                [len(column.label), *(len(str(r[index] or "")) for r in table.rows[:200])]
            )
            sheet.column_dimensions[get_column_letter(position)].width = min(
                max(10, longest + 2), 60
            )
    if not tables:
        workbook.create_sheet("Datos")
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ── CSV ──────────────────────────────────────────────────────────────────


def to_csv(document: Document) -> bytes:
    """La primera tabla, separada por `;` y con BOM: así la abre bien Excel en español."""
    block = next((b for b in document.blocks if b.kind == "table" and b.table is not None), None)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    if block is not None and block.table is not None:
        selected = _selected(block.table, block.columns)
        writer.writerow([neutralize(c.label) for _, c in selected])
        for row in block.table.rows:
            writer.writerow(
                [
                    neutralize(v) if isinstance(v, str) else ("" if v is None else v)
                    for v in (row[i] for i, _ in selected)
                ]
            )
    return ("﻿" + buffer.getvalue()).encode("utf-8")


# ── PDF ──────────────────────────────────────────────────────────────────


def to_pdf(document: Document) -> bytes:
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        ListFlowable,
        ListItem,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    widest = max(
        (len(_selected(b.table, b.columns)) for b in document.blocks if b.table is not None),
        default=0,
    )
    pagesize = landscape(letter) if widest > 5 else letter
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=document.title[:200],
        author="SAVI",
        creator="SAVI",
    )
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=7.5, leading=9)
    head = ParagraphStyle("head", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    story: list[Any] = []
    if document.company:
        story.append(Paragraph(escape(document.company), styles["Normal"]))
    story.append(Paragraph(escape(document.title), styles["Title"]))
    story.append(Paragraph(escape(_stamp(document)), styles["Italic"]))
    story.append(Spacer(1, 0.4 * cm))
    for block in document.blocks:
        if block.kind == "heading":
            story.append(Paragraph(escape(block.text), styles["Heading2"]))
        elif block.kind == "paragraph":
            story.append(Paragraph(_inline_markup(block.text), styles["BodyText"]))
        elif block.kind == "bullets":
            story.append(
                ListFlowable(
                    cast(
                        "list[Any]",
                        [
                            ListItem(Paragraph(_inline_markup(i), styles["BodyText"]))
                            for i in block.items
                        ],
                    ),
                    bulletType="bullet",
                )
            )
        elif block.kind == "key_values":
            rows = [
                [
                    Paragraph(f"<b>{escape(k)}</b>", styles["BodyText"]),
                    Paragraph(escape(v), styles["BodyText"]),
                ]
                for k, v in block.pairs
            ]
            story.append(Table(rows, hAlign="LEFT"))
        elif block.kind == "table" and block.table is not None:
            table = block.table
            selected = _selected(table, block.columns)
            data = [[Paragraph(escape(c.label), head) for _, c in selected]]
            for row in table.rows:
                data.append(
                    [Paragraph(escape(_display(row[i], c.kind)), cell) for i, c in selected]
                )
            grid = Table(data, repeatRows=1)
            grid.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#B91C1C")),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D4D4D4")),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#FAFAFA")],
                        ),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(grid)
            story.append(Paragraph(escape(_total_note(table)), styles["Italic"]))
        story.append(Spacer(1, 0.3 * cm))
    pdf.build(story)
    return buffer.getvalue()


def _inline_markup(text: str) -> str:
    """Markdown mínimo (negrita y cursiva) a la marca de reportlab; el resto escapado."""
    from xml.sax.saxutils import escape

    safe = escape(text)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    return re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", safe)


# ── Word ─────────────────────────────────────────────────────────────────


def to_docx(document: Document) -> bytes:
    from docx import Document as WordDocument
    from docx.shared import Pt

    word = WordDocument()
    word.core_properties.author = "SAVI"
    word.core_properties.title = document.title[:200]
    if document.company:
        word.add_paragraph(document.company)
    word.add_heading(document.title, level=0)
    stamp = word.add_paragraph(_stamp(document))
    stamp.runs[0].italic = True
    for block in document.blocks:
        if block.kind == "heading":
            word.add_heading(block.text, level=2)
        elif block.kind == "paragraph":
            _add_markup_paragraph(word.add_paragraph(), block.text)
        elif block.kind == "bullets":
            for item in block.items:
                _add_markup_paragraph(word.add_paragraph(style="List Bullet"), item)
        elif block.kind == "key_values":
            grid = word.add_table(rows=0, cols=2)
            grid.style = "Light List"
            for key, value in block.pairs:
                cells = grid.add_row().cells
                cells[0].text, cells[1].text = key, value
                cells[0].paragraphs[0].runs[0].bold = True
        elif block.kind == "table" and block.table is not None:
            table = block.table
            selected = _selected(table, block.columns)
            grid = word.add_table(rows=1, cols=len(selected))
            grid.style = "Light Grid Accent 2"
            for position, (_, column) in enumerate(selected):
                grid.rows[0].cells[position].text = column.label
            for row in table.rows:
                cells = grid.add_row().cells
                for position, (index, column) in enumerate(selected):
                    cells[position].text = _display(row[index], column.kind)
            for row_cells in grid.rows:
                for cell in row_cells.cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(8)
            note = word.add_paragraph(_total_note(table))
            note.runs[0].italic = True
    buffer = io.BytesIO()
    word.save(buffer)
    return buffer.getvalue()


def _add_markup_paragraph(paragraph: Any, text: str) -> None:
    """Negrita con `**` y nada más: el texto del modelo nunca se interpreta como marca."""
    for index, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if part:
            run = paragraph.add_run(part)
            run.bold = index % 2 == 1


class FileRenderer(DocumentRenderer):
    _RENDERERS = {
        FileFormat.XLSX: to_xlsx,
        FileFormat.CSV: to_csv,
        FileFormat.PDF: to_pdf,
        FileFormat.DOCX: to_docx,
    }

    def render(self, document: Document, file_format: FileFormat) -> bytes:
        return self._RENDERERS[file_format](document)
