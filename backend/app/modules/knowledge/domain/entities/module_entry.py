"""ModuleEntry — overview de un módulo del ERP.

No describe cada formulario (eso lo hace FormEntry). Describe el módulo
como concepto: qué hace, qué workflows centrales tiene, qué etiquetas
lo identifican.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.domain.value_objects.module_code import ModuleCode


class ModuleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ModuleCode
    label: str = Field(min_length=1, description="Nombre humano del módulo (p.ej. 'Contabilidad').")
    purpose: str = Field(min_length=1, description="Qué hace el módulo, 1-3 frases.")
    tags: list[str] = Field(default_factory=list)
    main_workflows: list[str] = Field(
        default_factory=list, description="IDs de workflows centrales del módulo."
    )
    main_forms: list[str] = Field(
        default_factory=list, description="Nombres de formularios más usados/representativos."
    )
