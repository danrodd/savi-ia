"""Servidor de actualizaciones al que SAVI se mudó, en `%LOCALAPPDATA%\\SAVI\\updates\\server.json`.

Cuando el manifiesto firmado trae `update_url`, SAVI lee primero un manifiesto
con firma válida en esa carpeta y, solo entonces, anota la dirección acá. Desde
el siguiente arranque esa dirección manda sobre el `.env` y sobre la que trae
la instalación: así el cambio de dominio llega a todos sin reinstalar.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.modules.updates.domain.exceptions import UpdateError
from app.modules.updates.domain.value_objects import normalize_server_url

log = logging.getLogger(__name__)

POINTER_FILENAME = "server.json"


class FileServerPointer:
    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> str | None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return normalize_server_url(str(data["url"]))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError, UpdateError):
            # Un archivo dañado no tiene que dejar a SAVI sin servidor: se ignora.
            log.warning("Actualizaciones: %s no es legible; se ignora.", self._path.name)
            return None

    def write(self, url: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(f"{self._path.name}.tmp")
        temporary.write_text(json.dumps({"url": url}), encoding="utf-8")
        temporary.replace(self._path)
