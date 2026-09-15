"""`consultar_libre` solo para administradores de la base (Fase 1, A1).

La tool escribe el SELECT que le pidan sobre cualquier tabla del ERP: no
distingue esquemas ni módulos. En manos de un usuario con acceso solo a
Ventas alcanzaba para leer nómina o contabilidad, salteándose los permisos
que el ERP sí aplica en su propia interfaz.

`allowed_modules=None` significa "administrador de la base consultada, sin
filtro" (D3); cualquier conjunto concreto es un usuario acotado.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.chat.infrastructure.llm.tools import registry
from app.modules.chat.infrastructure.llm.tools.registry import build_savi_tools
from app.modules.knowledge.infrastructure.static_catalog import load_static_catalog


@pytest.fixture(autouse=True)
def _catalogo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "get_catalog", lambda: load_static_catalog(tmp_path))


def _nombres(allowed_modules: frozenset[ModuleCode] | None) -> set[str]:
    especificaciones = build_savi_tools(
        conversation_id=None, allowed_modules=allowed_modules, erp_database_id=None
    )
    return {spec.name for spec in especificaciones}


def test_admin_keeps_free_query() -> None:
    assert "consultar_libre" in _nombres(None)


def test_limited_user_does_not_get_free_query() -> None:
    assert "consultar_libre" not in _nombres(frozenset({ModuleCode.VENTA}))


def test_user_without_any_module_does_not_get_it_either() -> None:
    """Conjunto vacío es "sin módulos", no "sin filtro"."""
    assert "consultar_libre" not in _nombres(frozenset())


def test_the_other_tools_stay_for_everyone() -> None:
    """Quitar la consulta libre no puede dejar al usuario sin poder preguntar:
    `consultar_datos` sigue, acotada por el catálogo semántico."""
    acotado = _nombres(frozenset({ModuleCode.VENTA}))

    assert acotado == {"info_empresa", "consultar_datos", "consultar_conocimiento"}


def test_tool_count_stays_within_the_mcp_limit() -> None:
    """Sigue valiendo el tope de 4 tools (ver mcp_deferred_tools_gotcha.md)."""
    assert len(_nombres(None)) == 4
