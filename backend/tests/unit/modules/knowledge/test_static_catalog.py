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
    _write(contabilidad / "overview.json", {
        "code": "CONTABILIDAD",
        "label": "Contabilidad",
        "purpose": "x",
    })
    _write(contabilidad / "forms" / "broken.json", {
        "name": "frmRoto",
        "module": "CONTABILIDAD",
        "type": "CONSULTA",
        # description faltante → ValidationError
    })

    with pytest.raises(KnowledgeLoadError):
        load_static_catalog(tmp_path)


def test_workflow_filtrado_por_interseccion_de_modulos(tmp_path: Path) -> None:
    _make_minimal_catalog(tmp_path)
    cat = load_static_catalog(tmp_path)

    # Usuario con CUENTACOBRAR no tiene CONTABILIDAD → no ve el workflow.
    assert cat.get_workflow(
        "wf_cierre", allowed_modules=frozenset({ModuleCode.CUENTACOBRAR})
    ) is None

    # Usuario con CONTABILIDAD sí lo ve.
    assert cat.get_workflow(
        "wf_cierre", allowed_modules=frozenset({ModuleCode.CONTABILIDAD})
    ) is not None


def test_catalogo_real_generado_por_bootstrap_carga() -> None:
    """Smoke test sobre los datos reales generados por bootstrap_knowledge.

    Si falla, indica que el v2 trajo algo que el schema actual no soporta
    o que un archivo se corrompió. Vale como gate de regresión.
    """
    if not _REAL_DATA_ROOT.exists():
        pytest.skip("catálogo real no generado todavía (correr bootstrap)")
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
    # El top hit debería ser frmConciliacionBancaria.
    assert hits[0].form.name == "frmConciliacionBancaria"
