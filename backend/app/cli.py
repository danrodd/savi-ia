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


def download_embedding_model() -> None:
    """Descarga el modelo de embeddings a `.models/` (desarrollo).

    El instalador lo baja en staging; esto es el equivalente local para no
    depender de descargas en runtime.
    """
    from app.infrastructure.config import get_settings
    from app.modules.company_knowledge.infrastructure.embeddings import (
        download_embedding_model as _download,
    )
    from app.modules.company_knowledge.infrastructure.embeddings import (
        models_root,
    )

    settings = get_settings()
    target = models_root(settings.company_docs_model_dir)
    name = settings.company_docs_embedding_model
    print(f"Descargando {name} en {target} ...")
    _download(name, target)
    print("Modelo listo.")
