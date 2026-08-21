"""El CLI se lanza por su ejecutable, nunca por el shim de npm.

cmd.exe corta la línea de comandos en 8191 caracteres. El SDK manda el
system prompt por argv y el de SAVI mide más del doble, así que un turno
lanzado a través de `claude.cmd` muere con "La línea de comandos es
demasiado larga" y código 1 — mientras el diagnóstico, cuya consulta de
prueba mide 50 caracteres, sigue saliendo en verde.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.infrastructure import claude_cli


def _npm_prefix(root: Path, *, with_binary: bool) -> Path:
    shim = root / "claude.cmd"
    shim.write_text("@echo off", encoding="utf-8")
    if with_binary:
        binary = root / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"")
    return shim


def test_prefers_the_package_binary_over_the_shim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shim = _npm_prefix(tmp_path, with_binary=True)
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: str(shim))

    resolved = claude_cli.resolve_cli_path()

    assert resolved is not None
    assert resolved.endswith("claude.exe")


def test_falls_back_to_the_shim_when_the_binary_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un paquete a medio instalar no puede dejar a SAVI sin ninguna ruta."""
    shim = _npm_prefix(tmp_path, with_binary=False)
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: str(shim))

    assert claude_cli.resolve_cli_path() == str(shim)


def test_leaves_a_real_executable_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Es lo que deja el instalador nativo del CLI."""
    native = r"C:\Users\alguien\.local\bin\claude.exe"
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: native)

    assert claude_cli.resolve_cli_path() == native


def test_returns_none_when_there_is_no_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: None)

    assert claude_cli.resolve_cli_path() is None
