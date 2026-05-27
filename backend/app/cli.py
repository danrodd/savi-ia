"""Entry points para tareas comunes vía `uv run <task>`.

Declarados en `[project.scripts]` de `pyproject.toml`. uv los expone como
ejecutables del venv tras `uv sync`.
"""

from __future__ import annotations

import subprocess
import sys


def dev() -> None:
    # Sin --reload por diseño: el módulo chat lanza el binario claude.exe
    # como subproceso y monta un MCP server in-process por turno; el
    # watcher de uvicorn los mataría a mitad de stream.
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)


def lint() -> None:
    sys.exit(subprocess.call(["ruff", "check", "."]))


def fmt() -> None:
    sys.exit(subprocess.call(["ruff", "format", "."]))


def typecheck() -> None:
    sys.exit(subprocess.call([sys.executable, "-m", "pyright", "app"]))


def migrate() -> None:
    sys.exit(subprocess.call(["alembic", "upgrade", "head"]))
