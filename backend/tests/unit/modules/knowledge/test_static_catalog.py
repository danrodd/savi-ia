"""Tests del StaticKnowledgeCatalog y del loader.

Cubre:
- Carga exitosa de un catálogo mínimo armado en tmp_path.
- Carga del catálogo real generado por bootstrap (smoke test).
- Búsqueda por intención con scoring.
- Filtrado por módulos autorizados.
- Glosario sin filtro.
- Errores claros con archivos inválidos.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.knowledge.infrastructure.static_catalog import (
    KnowledgeLoadError,
    load_static_catalog,
)

_REAL_DATA_ROOT = Path(__file__).resolve().parents[4] / "app" / "modules" / "knowledge" / "data"


def _write(p: Path, content: dict | list) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")


def _make_minimal_catalog(root: Path) -> None:
    contabilidad = root / "modules" / "contabilidad"
    _write(
        contabilidad / "overview.json",
        {
            "code": "CONTABILIDAD",
            "label": "Contabilidad",
            "purpose": "Libro contable y reportes financieros.",
            "tags": ["PUC"],
            "main_workflows": [],
            "main_forms": ["frmConsultaSaldoContable"],
        },
    )
    _write(
        contabilidad / "forms" / "frmConsultaSaldoContable.json",
        {
            "name": "frmConsultaSaldoContable",
            "module": "CONTABILIDAD",
            "type": "CONSULTA",
            "description": "Consulta saldos contables por cuenta del PUC.",
            "keywords": ["saldos", "balance"],
            "synonyms": ["consultar saldo", "ver balance"],
        },
    )
    _write(
        contabilidad / "workflows" / "wf_cierre.json",
        {
            "id": "wf_cierre",
            "name": "Cierre contable mensual",
            "description": "Cierre del periodo.",
            "modules": ["CONTABILIDAD"],
            "steps": [
                {"step": 1, "form": "frmConsultaSaldoContable", "action": "Revisar"},
            ],
        },
    )
    _write(
        root / "shared" / "glossary.json",
        [
            {
                "term": "DIAN",
                "definition": "Dirección de Impuestos y Aduanas Nacionales.",
                "aliases": ["dian"],
            },
        ],
    )
    _write(
        root / "shared" / "faqs" / "faq_permisos.json",
        {
            "id": "faq_permisos",
            "question": "¿Cómo asignar permisos a un usuario?",
            "synonyms": [],
            "module": None,
            "answer_summary": "frmPermisoAccionUsuario (módulo Seguridad).",
            "related_forms": ["frmPermisoAccionUsuario"],
            "related_workflows": [],
        },
    )


def test_catalogo_minimo_carga(tmp_path: Path) -> None:
    _make_minimal_catalog(tmp_path)
    cat = load_static_catalog(tmp_path)
    assert cat.describe_module(ModuleCode.CONTABILIDAD, allowed_modules=None) is not None
    assert cat.get_form("frmConsultaSaldoContable", allowed_modules=None) is not None
    assert cat.get_workflow("wf_cierre", allowed_modules=None) is not None
    assert cat.translate_term("DIAN") is not None


def test_busqueda_por_intencion_matchea_keywords_y_sinonimos(tmp_path: Path) -> None:
    _make_minimal_catalog(tmp_path)
    cat = load_static_catalog(tmp_path)

    hits = cat.search_by_intent("consultar saldo contable", allowed_modules=None, limit=3)
    assert len(hits) == 1
    assert hits[0].form.name == "frmConsultaSaldoContable"
    assert hits[0].score > 0


def test_filtrado_por_modulos_oculta_lo_no_autorizado(tmp_path: Path) -> None:
    _make_minimal_catalog(tmp_path)
    cat = load_static_catalog(tmp_path)

    # Usuario sin CONTABILIDAD → no debe ver el formulario.
    allowed = frozenset({ModuleCode.INVENTARIO})

    assert cat.get_form("frmConsultaSaldoContable", allowed_modules=allowed) is None
    assert cat.describe_module(ModuleCode.CONTABILIDAD, allowed_modules=allowed) is None
    assert cat.list_forms_by_module(ModuleCode.CONTABILIDAD, allowed_modules=allowed) == []
    assert cat.search_by_intent("saldo", allowed_modules=allowed, limit=3) == []


def test_faqs_compartidas_en_shared_se_cargan(tmp_path: Path) -> None:
    """Regresión: el loader solo recorría `modules/<slug>/faqs/`. Las FAQs
    transversales en `shared/faqs/` (sin módulo dueño) nunca se cargaban,
    así que preguntas como "¿cómo asigno permisos a un usuario?" nunca
    resolvían aunque la FAQ existiera en el catálogo real."""
    _make_minimal_catalog(tmp_path)
    cat = load_static_catalog(tmp_path)
    hits = cat.answer_faq("¿Cómo le asigno permisos a un usuario?", allowed_modules=None)
    assert len(hits) == 1
    assert hits[0].id == "faq_permisos"


def test_glosario_es_transversal(tmp_path: Path) -> None:
    _make_minimal_catalog(tmp_path)
    cat = load_static_catalog(tmp_path)

    # El glosario no se filtra por módulos.
    entry = cat.translate_term("dian")  # case-insensitive
    assert entry is not None
    assert entry.term == "DIAN"


def test_archivo_invalido_falla_loud(tmp_path: Path) -> None:
    # FormEntry sin description (campo requerido).
    contabilidad = tmp_path / "modules" / "contabilidad"
    _write(
        contabilidad / "overview.json",
        {
            "code": "CONTABILIDAD",
            "label": "Contabilidad",
            "purpose": "x",
        },
    )
    _write(
        contabilidad / "forms" / "broken.json",
        {
            "name": "frmRoto",
            "module": "CONTABILIDAD",
            "type": "CONSULTA",
            # description faltante → ValidationError
        },
    )

    with pytest.raises(KnowledgeLoadError):
        load_static_catalog(tmp_path)


def test_workflow_filtrado_por_interseccion_de_modulos(tmp_path: Path) -> None:
    _make_minimal_catalog(tmp_path)
    cat = load_static_catalog(tmp_path)

    # Usuario con CUENTACOBRAR no tiene CONTABILIDAD → no ve el workflow.
    assert (
        cat.get_workflow("wf_cierre", allowed_modules=frozenset({ModuleCode.CUENTACOBRAR})) is None
    )

    # Usuario con CONTABILIDAD sí lo ve.
    assert (
        cat.get_workflow("wf_cierre", allowed_modules=frozenset({ModuleCode.CONTABILIDAD}))
        is not None
    )


def test_catalogo_real_generado_por_bootstrap_carga() -> None:
    """Smoke test sobre los datos reales generados por bootstrap_knowledge.

    Si falla, indica que el v2 trajo algo que el schema actual no soporta
    o que un archivo se corrompió. Vale como gate de regresión.
    """
    # Se comprueba el contenido y no la existencia del directorio: el
    # repositorio versiona el esqueleto de `data/` (README y carpetas),
    # así que "existe" dejó de implicar "tiene catálogo".
    if not any(_REAL_DATA_ROOT.rglob("*.json")):
        pytest.skip("catálogo real no generado todavía (correr bootstrap_knowledge)")
    cat = load_static_catalog(_REAL_DATA_ROOT)

    # Sanity checks contra el catálogo real.
    assert cat.describe_module(ModuleCode.CONTABILIDAD, allowed_modules=None) is not None
    assert cat.describe_module(ModuleCode.INVENTARIO, allowed_modules=None) is not None

    # Búsqueda por intención típica del usuario.
    hits = cat.search_by_intent(
        "necesito conciliar el extracto bancario",
        allowed_modules=None,
        limit=3,
    )
    assert len(hits) > 0

    # Las FAQs transversales de `shared/faqs/` (sin módulo dueño) se cargan.
    faq_hits = cat.answer_faq("¿Cómo le asigno permisos a un usuario?", allowed_modules=None)
    assert len(faq_hits) > 0

    # El top hit debería ser frmConciliacionBancaria.
    assert hits[0].form.name == "frmConciliacionBancaria"


# ── Glosario real ────────────────────────────────────────────────────────


def test_el_glosario_real_carga_y_resuelve_las_siglas_del_dominio() -> None:
    catalog = load_static_catalog(_REAL_DATA_ROOT)

    for sigla in ("DIAN", "NIT", "PUC", "PILA", "INVIMA", "SOAT", "UVT", "CUFE"):
        assert catalog.translate_term(sigla) is not None, sigla


def test_el_glosario_ignora_tildes_mayusculas_y_puntos() -> None:
    catalog = load_static_catalog(_REAL_DATA_ROOT)

    entry = catalog.translate_term("retencion en la fuente")
    assert entry is not None and entry.term == "Retención en la fuente"
    assert catalog.translate_term("R.U.T.") == catalog.translate_term("rut")
    assert catalog.translate_term("Retefuente") == entry


def test_ningun_alias_apunta_a_dos_terminos() -> None:
    """Si dos entradas comparten un alias, la última pisa a la primera en
    silencio y el usuario recibe la definición equivocada."""
    raw = json.loads((_REAL_DATA_ROOT / "shared" / "glossary.json").read_text(encoding="utf-8"))
    from app.modules.knowledge.infrastructure.static_catalog import _term_key

    owners: dict[str, str] = {}
    for item in raw:
        for key in [item["term"], *item["aliases"]]:
            normalized = _term_key(key)
            assert owners.setdefault(normalized, item["term"]) == item["term"], key
