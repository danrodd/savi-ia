"""Archivos que dejan los intentos de instalación, en `%LOCALAPPDATA%\\SAVI\\updates\\`.

- `last-install.json`: lo escribe el vigilante (un proceso aparte) en cada paso.
- `history.jsonl`: una línea por intento ya resuelto; lo escribe SAVI.
- `install-<intento>.log`: el log de Inno Setup de cada intento.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.modules.updates.domain.exceptions import UpdateError
from app.modules.updates.domain.interfaces import InstallHistory, InstallResultReader
from app.modules.updates.domain.value_objects import (
    HISTORY_LIMIT,
    InstallRecord,
    InstallResult,
)

log = logging.getLogger(__name__)

RESULT_FILENAME = "last-install.json"
HISTORY_FILENAME = "history.jsonl"
# Los logs de Inno son chicos pero se acumulan: se guardan los últimos.
INSTALL_LOGS_KEPT = 5


class FileInstallResultReader(InstallResultReader):
    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> InstallResult | None:
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            log.warning("Actualizaciones: no se pudo leer %s.", self._path.name, exc_info=True)
            return None
        try:
            return InstallResult.from_mapping(json.loads(text))
        except (ValueError, UpdateError):
            # Un archivo ilegible no tiene que impedir que SAVI arranque.
            log.warning("Actualizaciones: %s no es legible; se ignora.", self._path.name)
            return None


class FileInstallHistory(InstallHistory):
    def __init__(self, path: Path, *, limit: int = HISTORY_LIMIT) -> None:
        self._path = path
        self._limit = limit

    def append(self, record: InstallRecord) -> None:
        lines = [
            json.dumps(item.to_mapping(), ensure_ascii=False)
            for item in [*reversed(self.recent(self._limit)), record]
        ][-self._limit :]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(f"{self._path.name}.tmp")
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temporary.replace(self._path)

    def recent(self, limit: int) -> list[InstallRecord]:
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError:
            log.warning("Actualizaciones: no se pudo leer el historial.", exc_info=True)
            return []
        records: list[InstallRecord] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                records.append(InstallRecord.from_mapping(json.loads(line)))
            except (ValueError, UpdateError):
                log.warning("Actualizaciones: una línea del historial no es legible; se omite.")
        return list(reversed(records))[:limit]


def install_log_path(updates_dir: Path, attempt_id: str) -> Path:
    return updates_dir / f"install-{attempt_id}.log"


def prune_install_logs(updates_dir: Path, *, keep: int = INSTALL_LOGS_KEPT) -> None:
    """Borra los logs de instalación más viejos, dejando `keep`."""
    logs = sorted(
        updates_dir.glob("install-*.log"), key=lambda path: path.stat().st_mtime, reverse=True
    )
    for old in logs[keep:]:
        old.unlink(missing_ok=True)


def delete_downloaded_installers(updates_dir: Path) -> None:
    """Después de instalar, el instalador descargado (unos 160 MB) ya no sirve."""
    for installer in updates_dir.glob("SAVI-Setup-*"):
        installer.unlink(missing_ok=True)
