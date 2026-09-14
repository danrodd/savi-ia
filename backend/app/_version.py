"""Versión de SAVI en runtime. No se escribe a mano: sale del tag de git.

La única fuente es `scripts/version.py` (raíz del monorepo). Este módulo
solo la resuelve, en este orden:

1. **Instalación empaquetada** — `app/_build_version.py`, generado por
   `installer/build.ps1` antes de PyInstaller. El equipo del cliente no
   tiene `.git`, así que la versión tiene que viajar incrustada.
2. **Desarrollo** — ejecuta `scripts/version.py` sobre el repositorio.
3. **Ninguna de las dos** — `0.0.0-dev`. Nunca un número que parezca
   real: un build que afirma ser `1.0.0` sin serlo manda a buscar el
   problema a la versión equivocada.

Quién la usa: `GET /version`, `GET /health`, el log de arranque y el
diagnóstico del launcher. Ver `installer/README.md#versionado`.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path

DEV_VERSION = "0.0.0-dev"

logger = logging.getLogger(__name__)


def _from_build() -> tuple[str, str | None, str | None] | None:
    # Por nombre y no con `from app import …`: el módulo solo existe dentro
    # de un build. Figura en los hiddenimports de installer/savi.spec.
    try:
        build = importlib.import_module("app._build_version")
    except ImportError:
        return None
    return (
        str(getattr(build, "VERSION", DEV_VERSION)),
        str(getattr(build, "COMMIT", "")) or None,
        str(getattr(build, "BUILT_AT", "")) or None,
    )


def _from_git() -> tuple[str, str | None, str | None] | None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "version.py"
    if not script.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_savi_version_script", script)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` busca el módulo en `sys.modules` mientras se ejecuta:
    # sin registrarlo antes, la carga falla con un AttributeError.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        return module.describe(), module.short_commit(), None
    except Exception:  # noqa: BLE001 — sin git o sin repo, la app arranca igual
        logger.debug("No se pudo calcular la versión desde git.", exc_info=True)
        return None


def _resolve() -> tuple[str, str | None, str | None]:
    return _from_build() or _from_git() or (DEV_VERSION, None, None)


__version__, __commit__, __built_at__ = _resolve()
