"""Resolución de recursos que funciona en desarrollo y empaquetado.

PyInstaller extrae los archivos de datos a un directorio temporal y lo
expone en `sys._MEIPASS`. Todo lo que se lea del disco por ruta relativa
(alembic, el catálogo de conocimiento, el build del frontend) tiene que
pasar por acá o funciona en `uv run dev` y falla en el .exe.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_dir() -> Path:
    """Raíz de los recursos de solo lectura.

    En desarrollo es `backend/`; empaquetado es el directorio de
    extracción. Las rutas de datos del .spec se declaran relativas a esta
    raíz para que ambos casos coincidan.
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle is not None:
        return Path(str(bundle))
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Directorio escribible por el usuario para BD y logs.

    Se resuelve en **runtime**, no en la instalación: si IT instala con
    una cuenta de administrador, el `%LOCALAPPDATA%` del instalador es el
    del administrador y no el de quien después usa la aplicación.
    Program Files tampoco sirve, no es escribible sin privilegios.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    target = root / "SAVI"
    target.mkdir(parents=True, exist_ok=True)
    return target


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) is True
