"""Registro neutral de tools: forma, schemas y normalización de resultados.

Las tools se definen una sola vez para todos los proveedores, así que el
schema es el contrato que ve cualquier modelo y tiene que ser un JSON
Schema válido y completo.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import validator_for

from app.modules.chat.domain.entities import ToolSpec
from app.modules.chat.infrastructure.llm.tools import registry
from app.modules.chat.infrastructure.llm.tools.knowledge import KNOWLEDGE_TIPOS
from app.modules.chat.infrastructure.llm.tools.registry import (
    build_savi_tools,
    to_tool_result,
)
from app.modules.chat.infrastructure.llm.tools.schemas import (
    CONSULTAR_CONOCIMIENTO_SCHEMA,
    CONSULTAR_DATOS_SCHEMA,
)
from app.modules.data_query.domain.semantic_query import FilterOp, QueryMode
from app.modules.knowledge.infrastructure.static_catalog import load_static_catalog


@pytest.fixture
def tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, ToolSpec]:
    catalog = load_static_catalog(tmp_path)
    monkeypatch.setattr(registry, "get_catalog", lambda: catalog)
    specs = build_savi_tools(conversation_id=None, allowed_modules=None, erp_database_id=None)
    return {spec.name: spec for spec in specs}


def test_registry_exposes_exactly_the_four_tools(tools: dict[str, ToolSpec]) -> None:
    assert set(tools) == {
        "info_empresa",
        "consultar_datos",
        "consultar_libre",
        "consultar_conocimiento",
    }


def test_every_schema_is_a_valid_object_json_schema(tools: dict[str, ToolSpec]) -> None:
    for spec in tools.values():
        validator_for(spec.parameters).check_schema(spec.parameters)
        assert spec.parameters["type"] == "object", spec.name
        assert "properties" in spec.parameters, spec.name


def test_enums_come_from_the_domain() -> None:
    consulta = CONSULTAR_DATOS_SCHEMA["properties"]["consulta"]["properties"]
    assert consulta["modo"]["enum"] == [m.value for m in QueryMode]
    assert consulta["filtros"]["items"]["properties"]["op"]["enum"] == [o.value for o in FilterOp]
    assert CONSULTAR_CONOCIMIENTO_SCHEMA["properties"]["tipo"]["enum"] == list(KNOWLEDGE_TIPOS)


def test_consultar_datos_schema_accepts_a_realistic_query() -> None:
    query: dict[str, Any] = {
        "consulta": {
            "entidad": "terceros",
            "modo": "detalle",
            "campos": ["id", "nombre"],
            "filtros": [{"campo": "nombre", "op": "contiene", "valor": "farma"}],
            "orden": {"campo": "nombre", "dir": "asc"},
            "limite": 10,
        }
    }
    validator = validator_for(CONSULTAR_DATOS_SCHEMA)(CONSULTAR_DATOS_SCHEMA)
    assert list(validator.iter_errors(query)) == []


# ── Normalización de resultados ─────────────────────────────────────


def test_mcp_result_keeps_text_and_camel_case_error_flag() -> None:
    result = to_tool_result(
        {"content": [{"type": "text", "text": "fallo del ERP"}], "isError": True}
    )
    assert result.text == "fallo del ERP"
    assert result.is_error is True


def test_mcp_result_without_error_flag_is_not_an_error() -> None:
    result = to_tool_result({"content": [{"type": "text", "text": "ok"}]})
    assert result.is_error is False


def test_raw_knowledge_dict_is_serialized_instead_of_dropped() -> None:
    """Regresión: el SDK de Claude descartaba en silencio todo resultado
    sin `content`, y el catálogo de conocimiento le llegaba vacío al
    modelo."""
    raw = {"matches": [{"score": 0.9, "form": {"nombre": "Factura de venta"}}]}

    result = to_tool_result(raw)

    assert json.loads(result.text) == raw
    assert result.is_error is False


def test_unknown_knowledge_tipo_is_flagged_as_error() -> None:
    result = to_tool_result({"error": "Tipo 'x' no reconocido."})
    assert result.is_error is True


async def test_invalid_argument_comes_back_as_an_error_result(
    tools: dict[str, ToolSpec],
) -> None:
    # Con un argumento inválido el impl responde error sin tocar la base.
    result = await tools["consultar_datos"].handler({"consulta": "no es un objeto"})
    assert result.is_error is True


async def test_handler_exception_returns_an_error_instead_of_raising() -> None:
    async def boom(_args: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("se cayó la conexión")

    spec = registry._spec("info_empresa", "x", {"type": "object", "properties": {}}, boom)  # pyright: ignore[reportPrivateUsage]

    result = await spec.handler({})

    assert result.is_error is True
    assert "se cayó la conexión" in result.text
