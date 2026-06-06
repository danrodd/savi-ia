"""Puerto del catálogo de conocimiento.

Define lo que la capa de aplicación necesita sin acoplarse a la
implementación (que hoy es archivos JSON cargados en memoria, mañana
puede ser BD, RAG, etc.).

Todas las búsquedas reciben `allowed_modules` y deben filtrar por ahí:
no devolver contenido de módulos fuera del set del usuario. Pasar `None`
significa "admin / sin filtro".
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.knowledge.domain.entities import (
    FaqEntry,
    FormEntry,
    GlossaryEntry,
    ModuleEntry,
    WorkflowEntry,
)


@dataclass(frozen=True, slots=True)
class SearchHit:
    """Un resultado de búsqueda libre, con score determinístico."""

    form: FormEntry
    score: int


class KnowledgeCatalog(ABC):
    @abstractmethod
    def search_by_intent(
        self,
        query: str,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
        limit: int = 3,
    ) -> list[SearchHit]:
        """Busca formularios que matcheen la intención del usuario."""

    @abstractmethod
    def get_form(
        self,
        name: str,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
    ) -> FormEntry | None:
        """Lookup directo por nombre interno. Retorna None si no existe o
        si el form pertenece a un módulo fuera del set del usuario."""

    @abstractmethod
    def list_forms_by_module(
        self,
        module: ModuleCode,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
    ) -> list[FormEntry]:
        """Lista los formularios de un módulo. Retorna vacío si el módulo
        no está permitido."""

    @abstractmethod
    def describe_module(
        self,
        module: ModuleCode,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
    ) -> ModuleEntry | None: ...

    @abstractmethod
    def get_workflow(
        self,
        workflow_id: str,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
    ) -> WorkflowEntry | None: ...

    @abstractmethod
    def answer_faq(
        self,
        question: str,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
        limit: int = 3,
    ) -> list[FaqEntry]:
        """Busca FAQs por match en pregunta y sinónimos."""

    @abstractmethod
    def translate_term(self, term: str) -> GlossaryEntry | None:
        """Lookup en el glosario (transversal, sin filtro de módulos)."""

    @abstractmethod
    def list_modules(
        self,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
    ) -> list[ModuleEntry]:
        """Lista los módulos del ERP a los que el usuario tiene acceso."""
