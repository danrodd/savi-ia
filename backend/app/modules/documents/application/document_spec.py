"""La especificación de un documento que entrega el modelo, validada.

El modelo describe; el servidor arma (ver `docs/plataforma/12-generacion-de-
documentos.md`, §3). Lo que no está acá no existe: no hay bloque de HTML, de
imagen ni de enlace. Las tablas no traen filas, traen la referencia de un
conjunto de resultados de la misma conversación.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_BLOCKS = 200
MAX_TABLES = 10


class _Block(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HeadingBlock(_Block):
    tipo: Literal["titulo2"]
    texto: str = Field(min_length=1, max_length=200)


class ParagraphBlock(_Block):
    tipo: Literal["parrafo"]
    texto: str = Field(min_length=1, max_length=4000)


class BulletsBlock(_Block):
    tipo: Literal["lista"]
    items: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        min_length=1, max_length=50
    )


class KeyValuesBlock(_Block):
    tipo: Literal["datos_clave"]
    items: list[
        tuple[Annotated[str, Field(max_length=100)], Annotated[str, Field(max_length=200)]]
    ] = Field(min_length=1, max_length=30)


class TableBlock(_Block):
    tipo: Literal["tabla"]
    conjunto: UUID
    columnas: list[Annotated[str, Field(max_length=100)]] = Field(
        default_factory=list, max_length=40
    )


class ChartBlock(_Block):
    """Gráfico de una columna numérica de un conjunto, por otra columna de etiquetas."""

    tipo: Literal["grafico"]
    forma: Literal["barras", "torta", "lineas"] = "barras"
    conjunto: UUID
    etiqueta: str = Field(min_length=1, max_length=100)
    valor: str = Field(min_length=1, max_length=100)
    titulo: str | None = Field(default=None, max_length=150)


DocumentBlockSpec = Annotated[
    HeadingBlock | ParagraphBlock | BulletsBlock | KeyValuesBlock | TableBlock | ChartBlock,
    Field(discriminator="tipo"),
]


class DocumentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formato: Literal["pdf", "docx"]
    titulo: str = Field(min_length=1, max_length=150)
    bloques: list[DocumentBlockSpec] = Field(min_length=1, max_length=MAX_BLOCKS)

    def table_ids(self) -> list[UUID]:
        return [b.conjunto for b in self.bloques if isinstance(b, TableBlock | ChartBlock)]
