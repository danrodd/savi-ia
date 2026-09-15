from pathlib import Path

from app.paths import is_frozen, resource_dir


def models_root(configured: str) -> Path:
    """Raíz del caché de modelos.

    Instalado: `<app>/models/` (empaquetado por el instalador). Desarrollo:
    `backend/.models/`, bajado con `uv run download-embedding-model`. Un
    `COMPANY_DOCS_MODEL_DIR` explícito gana en ambos casos.
    """
    if configured.strip():
        return Path(configured).expanduser().resolve()
    if is_frozen():
        return resource_dir() / "models"
    return resource_dir() / ".models"
