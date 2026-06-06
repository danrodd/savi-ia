"""FaqEntry — pregunta natural pre-mapeada a respuesta y formularios.

Atajos para preguntas muy frecuentes que justifican respuesta canónica
sin pasar por búsqueda completa. Vienen del `question_to_form_map` del
JSON v2.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.domain.value_objects.module_code import ModuleCode


class FaqEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    question: str = Field(min_length=1)
    synonyms: list[str] = Field(default_factory=list)
    module: ModuleCode | None = Field(
        default=None, description="Si la FAQ es específica de un módulo. None = transversal."
    )
    answer_summary: str = Field(min_length=1)
    related_forms: list[str] = Field(default_factory=list)
    related_workflows: list[str] = Field(default_factory=list)
