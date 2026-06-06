"""StaticKnowledgeCatalog — loader del catálogo desde archivos JSON.

Pipeline al boot:
1. Recorre `<root>/modules/<dossier>/{overview.json,forms/*.json,workflows/*.json,faqs/*.json}`
   y `<root>/shared/{glossary.json, ...}`.
2. Cada archivo se valida con su modelo Pydantic correspondiente.
3. Si **cualquier archivo es inválido**, falla LOUD con `KnowledgeLoadError`
   — no se arranca con conocimiento corrupto.
4. Construye índices en memoria: por nombre de form, por módulo, por id
   de workflow, por término del glosario.

El catálogo queda inmutable (no recarga en runtime). Para refrescar
hay que reiniciar el backend, lo cual está bien porque los archivos
viajan en el repo y los cambios se aplican por deploy.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.knowledge.domain.entities import (
    FaqEntry,
    FormEntry,
    GlossaryEntry,
    ModuleEntry,
    WorkflowEntry,
)
from app.modules.knowledge.domain.interfaces import KnowledgeCatalog, SearchHit


class KnowledgeLoadError(Exception):
    """Error fatal: un archivo del catálogo no valida o falta info clave."""


class StaticKnowledgeCatalog(KnowledgeCatalog):
    def __init__(
        self,
        modules: list[ModuleEntry],
        forms: list[FormEntry],
        workflows: list[WorkflowEntry],
        faqs: list[FaqEntry],
        glossary: list[GlossaryEntry],
    ) -> None:
        self._modules_by_code: dict[ModuleCode, ModuleEntry] = {m.code: m for m in modules}
        self._forms_by_name: dict[str, FormEntry] = {f.name: f for f in forms}
        self._forms_by_module: dict[ModuleCode, list[FormEntry]] = defaultdict(list)
        for f in forms:
            self._forms_by_module[f.module].append(f)
        self._workflows_by_id: dict[str, WorkflowEntry] = {w.id: w for w in workflows}
        self._faqs: list[FaqEntry] = list(faqs)
        self._glossary_by_key: dict[str, GlossaryEntry] = {}
        for g in glossary:
            self._glossary_by_key[g.term.lower()] = g
            for alias in g.aliases:
                self._glossary_by_key[alias.lower()] = g

    # ─── Helpers de autorización ──────────────────────────────────────

    @staticmethod
    def _module_allowed(module: ModuleCode | None, allowed: frozenset[ModuleCode] | None) -> bool:
        if allowed is None:
            return True
        if module is None:
            return True
        return module in allowed

    # ─── API pública ──────────────────────────────────────────────────

    def search_by_intent(
        self,
        query: str,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
        limit: int = 3,
    ) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for form in self._forms_by_name.values():
            if not self._module_allowed(form.module, allowed_modules):
                continue
            score = form.matches_query(query)
            if score > 0:
                hits.append(SearchHit(form=form, score=score))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def get_form(
        self,
        name: str,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
    ) -> FormEntry | None:
        form = self._forms_by_name.get(name)
        if form is None:
            return None
        if not self._module_allowed(form.module, allowed_modules):
            return None
        return form

    def list_forms_by_module(
        self,
        module: ModuleCode,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
    ) -> list[FormEntry]:
        if not self._module_allowed(module, allowed_modules):
            return []
        return list(self._forms_by_module.get(module, []))

    def describe_module(
        self,
        module: ModuleCode,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
    ) -> ModuleEntry | None:
        if not self._module_allowed(module, allowed_modules):
            return None
        return self._modules_by_code.get(module)

    def get_workflow(
        self,
        workflow_id: str,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
    ) -> WorkflowEntry | None:
        wf = self._workflows_by_id.get(workflow_id)
        if wf is None:
            return None
        # El workflow se devuelve si AL MENOS UN módulo intersecta —
        # son procesos cross-módulo y un usuario con parte del flow
        # igual puede beneficiarse de ver el panorama completo.
        if (
            allowed_modules is not None
            and wf.modules
            and not any(m in allowed_modules for m in wf.modules)
        ):
            return None
        return wf

    def answer_faq(
        self,
        question: str,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
        limit: int = 3,
    ) -> list[FaqEntry]:
        q = question.lower().strip()
        if not q:
            return []
        tokens = [t for t in q.replace("?", "").split() if len(t) > 2]
        if not tokens:
            return []
        hits: list[tuple[FaqEntry, int]] = []
        for faq in self._faqs:
            if not self._module_allowed(faq.module, allowed_modules):
                continue
            score = 0
            target = (faq.question + " " + " ".join(faq.synonyms)).lower()
            for tok in tokens:
                if tok in target:
                    score += 2
            if score > 0:
                hits.append((faq, score))
        hits.sort(key=lambda h: h[1], reverse=True)
        return [h[0] for h in hits[:limit]]

    def translate_term(self, term: str) -> GlossaryEntry | None:
        return self._glossary_by_key.get(term.lower().strip())

    def list_modules(
        self,
        *,
        allowed_modules: frozenset[ModuleCode] | None,
    ) -> list[ModuleEntry]:
        return [
            m
            for code, m in self._modules_by_code.items()
            if self._module_allowed(code, allowed_modules)
        ]


# ──────────────────────────────────────────────────────────────────────
# Loader
# ──────────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> Any:
    """Lee JSON. Tipo `Any` porque el callsite valida el shape esperado
    (dict u list) inmediatamente después y luego pasa por Pydantic."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise KnowledgeLoadError(f"JSON inválido en {path}: {e}") from e


def _parse_model[T: BaseModel](model: type[T], data: Any, path: Path) -> T:
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise KnowledgeLoadError(
            f"Validación falló para {path} (modelo {model.__name__}):\n{e}"
        ) from e


def _load_dir[T: BaseModel](
    root: Path, model: type[T], *, optional: bool = False
) -> list[T]:
    if not root.exists():
        if optional:
            return []
        raise KnowledgeLoadError(f"Directorio requerido faltante: {root}")
    items: list[T] = []
    for file in sorted(root.glob("*.json")):
        data = _read_json(file)
        if not isinstance(data, dict):
            raise KnowledgeLoadError(f"{file}: esperaba objeto JSON, llegó {type(data).__name__}")
        items.append(_parse_model(model, data, file))
    return items


def load_static_catalog(root: Path) -> StaticKnowledgeCatalog:
    """Carga el catálogo desde `<root>` y devuelve la instancia inmutable.

    Layout esperado:
        <root>/
        ├── modules/
        │   ├── <module_slug>/
        │   │   ├── overview.json          (ModuleEntry — opcional)
        │   │   ├── forms/*.json           (FormEntry)
        │   │   ├── workflows/*.json       (WorkflowEntry)
        │   │   └── faqs/*.json            (FaqEntry)
        └── shared/
            └── glossary.json              (list[GlossaryEntry])

    Cada `<module_slug>` debe coincidir (case-insensitive) con un valor
    de `ModuleCode`. Slugs desconocidos hacen fallar el load.
    """
    if not root.exists():
        raise KnowledgeLoadError(f"Knowledge root no existe: {root}")

    modules: list[ModuleEntry] = []
    forms: list[FormEntry] = []
    workflows: list[WorkflowEntry] = []
    faqs: list[FaqEntry] = []

    modules_dir = root / "modules"
    if modules_dir.exists():
        for dossier in sorted(p for p in modules_dir.iterdir() if p.is_dir()):
            overview_path = dossier / "overview.json"
            if overview_path.exists():
                modules.append(
                    _parse_model(ModuleEntry, _read_json(overview_path), overview_path)
                )
            forms.extend(_load_dir(dossier / "forms", FormEntry, optional=True))
            workflows.extend(_load_dir(dossier / "workflows", WorkflowEntry, optional=True))
            faqs.extend(_load_dir(dossier / "faqs", FaqEntry, optional=True))

    # Glosario: un único archivo con lista. Si no existe, glosario vacío.
    glossary: list[GlossaryEntry] = []
    glossary_path = root / "shared" / "glossary.json"
    if glossary_path.exists():
        raw: Any = _read_json(glossary_path)
        if not isinstance(raw, list):
            raise KnowledgeLoadError(
                f"{glossary_path}: esperaba lista de glossary entries, llegó {type(raw).__name__}"
            )
        items: list[Any] = list(raw)  # type: ignore[arg-type]
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise KnowledgeLoadError(f"{glossary_path}[{i}]: no es objeto")
            glossary.append(_parse_model(GlossaryEntry, item, glossary_path))

    return StaticKnowledgeCatalog(
        modules=modules,
        forms=forms,
        workflows=workflows,
        faqs=faqs,
        glossary=glossary,
    )
