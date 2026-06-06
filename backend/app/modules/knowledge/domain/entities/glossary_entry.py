"""GlossaryEntry — definición de un término o sigla del dominio.

Ej.: DIAN, PILA, NIT, PUC. Transversal: el LLM puede consultar el
glosario sin importar los módulos del usuario.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GlossaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    term: str = Field(min_length=1, description="Sigla o término (p.ej. 'DIAN').")
    definition: str = Field(min_length=1)
    aliases: list[str] = Field(
        default_factory=list, description="Otras formas en que se escribe/dice el término."
    )
