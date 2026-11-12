"""Documento a generar: título y bloques, sin formato de archivo.

Lo mismo sirve para exportar una tabla (un documento con un solo bloque de
tabla) y para un informe (P3). Las tablas llevan las filas del conjunto de
resultados, nunca texto escrito por el modelo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.modules.documents.domain.result_set import ResultSet

BlockKind = Literal["heading", "paragraph", "bullets", "key_values", "table"]


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    text: str = ""
    items: tuple[str, ...] = ()
    pairs: tuple[tuple[str, str], ...] = ()
    table: ResultSet | None = None
    # Columnas de la tabla a mostrar, en orden. Vacío = todas.
    columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class Document:
    title: str
    generated_at: datetime
    company: str | None = None
    blocks: tuple[Block, ...] = field(default_factory=tuple)

    @classmethod
    def for_table(
        cls, table: ResultSet, *, generated_at: datetime, company: str | None
    ) -> Document:
        return cls(
            title=table.title,
            generated_at=generated_at,
            company=company,
            blocks=(Block(kind="table", table=table),),
        )
