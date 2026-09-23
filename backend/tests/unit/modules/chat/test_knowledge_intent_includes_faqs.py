"""`tipo: "intencion"` tiene que mirar TODO el catálogo, no solo formularios.

Regresión de un bug con dos capas, encontrado probando Gemini con la misma
batería que Claude:

1. El loader nunca leía `shared/faqs/`, así que las FAQs transversales no
   existían en runtime (corregido en `static_catalog.py`).
2. Aun cargadas, solo se llegaba a ellas con `tipo: "faq"`. El modelo usa
   `tipo: "intencion"` por defecto — que recorre únicamente formularios —,
   así que "¿cómo le asigno permisos a un usuario?" seguía devolviendo
   formularios irrelevantes con score bajo (frmCierreMes) y el modelo
   improvisaba una respuesta inventada.

El síntoma que ve el usuario solo desaparece arreglando las dos.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.modules.chat.infrastructure.llm.tools.knowledge import (
    build_buscar_por_intencion_impl,
)
from app.modules.knowledge.infrastructure.static_catalog import load_static_catalog

_DATA_ROOT = Path(__file__).resolve().parents[4] / "app" / "modules" / "knowledge" / "data"


def _catalog() -> Any:
    if not any(_DATA_ROOT.rglob("*.json")):
        pytest.skip("catálogo real no generado todavía")
    return load_static_catalog(_DATA_ROOT)


@pytest.mark.asyncio
async def test_intent_search_surfaces_a_cross_cutting_faq() -> None:
    impl = build_buscar_por_intencion_impl(_catalog(), None)

    result = await impl({"consulta": "¿Cómo le asigno permisos a un usuario?"})

    faqs = result.get("faqs", [])
    assert faqs, "la FAQ transversal de permisos tiene que llegar por 'intencion'"
    assert any("permiso" in f["question"].lower() for f in faqs)


@pytest.mark.asyncio
async def test_intent_search_still_returns_forms() -> None:
    """El camino que ya funcionaba no se rompe: una consulta de formulario
    sigue devolviendo formularios."""
    impl = build_buscar_por_intencion_impl(_catalog(), None)

    result = await impl({"consulta": "necesito conciliar el extracto bancario"})

    assert result["matches"], "las búsquedas de formulario tienen que seguir andando"


@pytest.mark.asyncio
async def test_intent_search_with_no_match_explains_itself() -> None:
    impl = build_buscar_por_intencion_impl(_catalog(), None)

    result = await impl({"consulta": "zzzz qqqq xxxx"})

    assert result["matches"] == []
    assert "message" in result
