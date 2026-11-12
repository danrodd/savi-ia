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

BlockKind = Literal["heading", "paragraph", "bullets", "key_values", "table", "chart"]


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    text: str = ""
    items: tuple[str, ...] = ()
    pairs: tuple[tuple[str, str], ...] = ()
    table: ResultSet | None = None
    # Columnas de la tabla a mostrar, en orden. Vacío = todas. En un gráfico:
    # (columna de etiquetas, columna de valores).
    columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class Branding:
    """Nombre y logo (PNG ya validado) de la empresa, para el encabezado."""

    name: str | None = None
    logo_png: bytes | None = None


@dataclass(frozen=True)
class Document:
    title: str
    generated_at: datetime
    company: str | None = None
    blocks: tuple[Block, ...] = field(default_factory=tuple)
    logo_png: bytes | None = None

    @classmethod
    def for_table(
        cls, table: ResultSet, *, generated_at: datetime, branding: Branding | None = None
    ) -> Document:
        brand = branding or Branding()
        return cls(
            title=table.title,
            generated_at=generated_at,
            company=brand.name,
            blocks=(Block(kind="table", table=table),),
            logo_png=brand.logo_png,
        )
