"""FormEntry — la entidad más rica del catálogo.

Representa un formulario del ERP con toda la info que el LLM necesita
para responder al usuario en lenguaje natural: cómo llegar, qué hacer,
qué cálculos aplican, qué problemas comunes, qué formularios relacionados.

CASI TODOS LOS CAMPOS son opcionales — un formulario puede empezar
pobre (solo name + module + type + description + keywords, como vienen
del JSON v2) y enriquecerse gradualmente.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.knowledge.domain.entities.form_type import FormType


class HowToStep(BaseModel):
    """Un paso del procedimiento para usar el formulario."""

    model_config = ConfigDict(extra="forbid")

    step: int = Field(ge=1)
    action: str
    detail: str | None = None


class Calculation(BaseModel):
    """Una fórmula o cálculo de negocio que aplica al formulario."""

    model_config = ConfigDict(extra="forbid")

    name: str
    formula: str
    explanation: str | None = None


class CommonIssue(BaseModel):
    """Problema frecuente + cómo resolverlo."""

    model_config = ConfigDict(extra="forbid")

    problem: str
    solution: str


class FormEntry(BaseModel):
    """Una pantalla / formulario del ERP."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # ─── Identidad ────────────────────────────────────────────────────
    name: str = Field(
        min_length=1,
        description='Identificador interno (p.ej. "frmFactura"). No se muestra al usuario.',
    )
    module: ModuleCode = Field(description="Módulo del ERP al que pertenece.")
    type: FormType

    # ─── Lo que el usuario VE (siempre que esté autorizado) ───────────
    user_label: str | None = Field(
        default=None, description='Nombre humano del formulario (p.ej. "Factura de venta").'
    )
    description: str = Field(min_length=1, description="Resumen ejecutivo en 1-3 frases.")

    # ─── Matching de intención (lo que usa buscar_por_intencion) ──────
    synonyms: list[str] = Field(
        default_factory=list,
        description="Frases que el usuario podría usar para referirse a este formulario.",
    )
    keywords: list[str] = Field(
        default_factory=list, description="Palabras clave técnicas/negocio."
    )

    # ─── Navegación y procedimiento ───────────────────────────────────
    navigation_path: list[str] = Field(
        default_factory=list, description="Ruta del menú principal hasta este formulario."
    )
    prerequisites: list[str] = Field(
        default_factory=list, description="Qué debe estar listo antes de usarlo."
    )
    how_to: list[HowToStep] = Field(
        default_factory=list[HowToStep],
        description="Pasos ordenados para completar la operación.",
    )

    # ─── Operaciones y reglas ─────────────────────────────────────────
    actions: list[str] = Field(
        default_factory=list, description="Botones / verbos disponibles dentro del formulario."
    )
    filters: list[str] = Field(
        default_factory=list, description="Filtros de búsqueda/consulta disponibles."
    )
    business_rules: list[str] = Field(
        default_factory=list, description="Reglas de negocio (validaciones, restricciones)."
    )

    # ─── Cálculos y salidas ───────────────────────────────────────────
    calculations: list[Calculation] = Field(default_factory=list[Calculation])
    outputs: list[str] = Field(
        default_factory=list, description="Qué genera/produce el formulario."
    )

    # ─── Soporte ──────────────────────────────────────────────────────
    common_issues: list[CommonIssue] = Field(default_factory=list[CommonIssue])

    # ─── Cross-references ─────────────────────────────────────────────
    related_forms: list[str] = Field(
        default_factory=list, description="Otros formularios con los que se conecta."
    )
    related_workflows: list[str] = Field(
        default_factory=list, description="Workflows en los que participa."
    )
    db_tables: list[str] = Field(
        default_factory=list, description="Tablas del ERP que toca (referencia técnica)."
    )

    # ─── Metadata ─────────────────────────────────────────────────────
    source: str | None = Field(
        default=None, description="De dónde viene esta info (manual oficial, KB v2, etc)."
    )
    updated: str | None = Field(default=None, description="Fecha YYYY-MM-DD de última revisión.")

    def matches_query(self, query: str) -> int:
        """Score crudo de match contra una query libre.

        Compara contra `name`, `user_label`, `description`, `synonyms` y
        `keywords`. No es sofisticado — es un baseline determinístico.
        Mayor score = mejor match. 0 = sin match.

        Para casos avanzados (sinónimos semánticos, ranking ponderado por
        frecuencia, etc.) la Capa 2 (RAG) cubre la búsqueda no-trivial.
        """
        q = query.lower().strip()
        if not q:
            return 0
        tokens = [t for t in q.replace("?", "").replace(",", "").split() if len(t) > 2]
        if not tokens:
            return 0
        score = 0
        for tok in tokens:
            if tok in self.name.lower():
                score += 3
            if self.user_label and tok in self.user_label.lower():
                score += 4
            if tok in self.description.lower():
                score += 2
            for syn in self.synonyms:
                if tok in syn.lower():
                    score += 5
            for kw in self.keywords:
                if tok in kw.lower():
                    score += 4
        return score
