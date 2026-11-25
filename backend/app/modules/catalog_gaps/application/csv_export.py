"""CSV de los vacíos para abrir en Excel (es-CO): UTF-8 con BOM, separador `;` y
celdas de texto libre a salvo de la inyección de fórmulas."""

from __future__ import annotations

import csv
import io

from app.modules.catalog_gaps.domain.value_objects import CatalogGapReport, GapKind

_BOM = "﻿"
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

KIND_LABELS = {
    GapKind.FREE_QUERY: "Resuelta con consulta libre",
    GapKind.FAILED_QUERY: "Consulta fallida",
    GapKind.QUERY_LIMIT: "Llegó al tope de consultas",
}

CSV_HEADERS = ("Pregunta", "Qué pasó", "Veces", "Última vez", "Tablas del ERP", "Conversación")


def _safe(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_FORMULA_PREFIXES) else text


def build_gaps_csv(report: CatalogGapReport) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_HEADERS)
    for gap in report.gaps:
        writer.writerow(
            [
                _safe(gap.question),
                _safe(", ".join(KIND_LABELS[k] for k in gap.kinds)),
                gap.times,
                _safe(gap.last_at.isoformat(timespec="seconds")),
                _safe(", ".join(gap.tables)),
                _safe(gap.conversation_id),
            ]
        )
    return (_BOM + buffer.getvalue()).encode("utf-8")
