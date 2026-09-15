"""Regresión de seguridad: el CLI de Claude no puede traer sus herramientas.

Por qué existe: el runner pasaba `permission_mode="bypassPermissions"` con
`allowed_tools`, pero **sin** `tools`. En el Agent SDK `allowed_tools` solo
aprueba sin preguntar; el conjunto disponible lo define `tools`, y sin él el
CLI carga el suyo completo. Verificado leyendo el mensaje `init` del CLI con
las opciones reales del chat: aparecían 31 herramientas, entre ellas `Bash`,
`Read`, `Write` y `WebFetch`, todas auto-aprobadas.

Con eso, cualquier usuario autenticado podía pedirle al chat que leyera el
`.env` (llaves de cifrado del ERP y `JWT_SECRET`) o que ejecutara comandos en
la máquina donde corre SAVI. Ver `docs/seguridad/01-fase-0-cierre-urgente.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.infrastructure.config import Settings
from app.modules.chat.domain.interfaces import ActiveProvider
from app.modules.chat.infrastructure.llm.claude.mcp_adapter import (
    BUILTIN_TOOLS,
    MCP_SERVER_NAME,
)
from app.modules.chat.infrastructure.llm.claude.runner import _build_options
from app.modules.chat.infrastructure.llm.tools import registry
from app.modules.knowledge.infrastructure.static_catalog import load_static_catalog


@pytest.fixture
def provider() -> ActiveProvider:
    return ActiveProvider(
        kind="claude",
        chat_model="claude-sonnet-4-6",
        title_model="claude-haiku-4-5",
        credential_kind="local_session",
        credential=None,
    )


@pytest.fixture
def options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: ActiveProvider):
    catalog = load_static_catalog(tmp_path)
    monkeypatch.setattr(registry, "get_catalog", lambda: catalog)
    return _build_options(
        Settings(),
        provider,
        conversation_id=None,
        allowed_modules=None,
        erp_database_id=None,
        document_context=None,
    )


def test_builtin_tools_are_disabled(options) -> None:  # noqa: ANN001 — tipo del SDK
    """`tools=[]` es lo único que apaga Bash, Read, Write y compañía."""
    assert options.tools == [], (
        "El runner debe pasar `tools=[]`. Sin eso el CLI trae sus herramientas "
        "integradas y `bypassPermissions` las aprueba sin preguntar."
    )


def test_builtin_tools_are_also_denied(options) -> None:  # noqa: ANN001
    """Segunda barrera, por si un CLI futuro cambia el default de `--tools`."""
    denied = set(options.disallowed_tools)
    for dangerous in ("Bash", "Read", "Write", "Edit", "WebFetch"):
        assert dangerous in denied, f"{dangerous} debería estar en disallowed_tools"
    assert denied == set(BUILTIN_TOOLS)


def test_only_savi_tools_are_allowed(options) -> None:  # noqa: ANN001
    """Lo único aprobado son las tools propias del MCP server de SAVI."""
    assert options.allowed_tools, "Sin tools propias el agente no puede consultar nada"
    for name in options.allowed_tools:
        assert name.startswith(f"mcp__{MCP_SERVER_NAME}__"), (
            f"{name} no es una tool de SAVI: solo se aprueban las propias"
        )


@pytest.mark.asyncio
async def test_title_generator_has_no_tools(
    provider: ActiveProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El auto-título recibe texto del usuario y no necesita herramientas."""
    from app.modules.chat.infrastructure.llm.claude import title_generator as module

    captured: dict[str, object] = {}

    class _FakeOptions:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    async def _no_query(*_args: object, **_kwargs: object):  # noqa: ANN202
        # El título no interesa acá: lo que se verifica son las opciones.
        raise RuntimeError("sin CLI en tests")
        yield  # pragma: no cover — lo vuelve async generator

    monkeypatch.setattr(module, "ClaudeAgentOptions", _FakeOptions)
    monkeypatch.setattr(module, "query", _no_query)

    assert await module.ClaudeTitleGenerator(Settings(), provider).generate("hola") is None
    assert captured.get("tools") == []
    assert captured.get("allowed_tools") == []
    assert "Bash" in set(captured.get("disallowed_tools") or [])
