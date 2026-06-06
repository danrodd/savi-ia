"""WorkflowEntry — proceso de negocio end-to-end que cruza formularios."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.domain.value_objects.module_code import ModuleCode


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int = Field(ge=1)
    form: str = Field(description="Nombre del formulario que ejecuta el paso.")
    action: str = Field(description="Qué hace el usuario en este paso.")
    optional: bool = False
    detail: str | None = None


class WorkflowEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(description='Identificador único del workflow (p.ej. "wf_ciclo_venta").')
    name: str = Field(min_length=1, description="Nombre humano del proceso.")
    description: str = Field(min_length=1)
    modules: list[ModuleCode] = Field(
        default_factory=list[ModuleCode],
        description="Módulos involucrados en el workflow.",
    )
    synonyms: list[str] = Field(default_factory=list)
    steps: list[WorkflowStep] = Field(min_length=1)
