"""Versión publicada, manifiesto del canal y la decisión de qué mostrar.

Todo puro: no lee red ni disco. La firma del manifiesto se verifica antes, en
infraestructura; acá llega ya confiable y solo se valida su forma.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from functools import total_ordering
from urllib.parse import urlsplit

from app.modules.updates.domain.exceptions.exceptions import (
    InvalidManifestError,
    InvalidVersionError,
)

# `-rc.N` es una candidata: se prueba en `beta` y nunca llega a `stable`.
_VERSION = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-rc\.([1-9]\d*))?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Solo para probar en local con `python -m http.server`: fuera de este equipo
# el instalador viaja siempre por HTTPS.
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
NOTES_MAX_CHARS = 2000


def normalize_server_url(text: str) -> str:
    """La carpeta del servidor sin la barra final; exige HTTPS (o loopback, para probar)."""
    url = text.strip().rstrip("/")
    parts = urlsplit(url)
    loopback = parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS
    if (parts.scheme != "https" and not loopback) or not parts.hostname:
        raise InvalidManifestError("update_url no usa HTTPS.")
    return url


@total_ordering
@dataclass(frozen=True)
class ReleaseVersion:
    major: int
    minor: int
    patch: int
    # Número de candidata (`v1.4.0-rc.2` → 2). `None` es la versión final.
    rc: int | None = None

    @classmethod
    def parse(cls, text: str) -> ReleaseVersion:
        match = _VERSION.match(text.strip())
        if match is None:
            raise InvalidVersionError(text)
        rc = int(match[4]) if match[4] is not None else None
        return cls(int(match[1]), int(match[2]), int(match[3]), rc)

    @property
    def is_candidate(self) -> bool:
        return self.rc is not None

    def _key(self) -> tuple[int, int, int, int, int]:
        # Una candidata es anterior a su versión final:
        # v1.4.0-rc.1 < v1.4.0-rc.2 < v1.4.0 < v1.4.1-rc.1.
        if self.rc is None:
            return (self.major, self.minor, self.patch, 1, 0)
        return (self.major, self.minor, self.patch, 0, self.rc)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ReleaseVersion):
            return NotImplemented
        return self._key() < other._key()

    @classmethod
    def from_running(cls, text: str) -> ReleaseVersion | None:
        """La versión instalada, o `None` si no es un tag exacto.

        Un build de desarrollo (`v1.3.2-3-gabc1234`, `-sucio`, `0.0.0-dev`) no
        se actualiza solo: reemplazarlo por el instalador publicado borraría
        lo que se está probando. Una candidata exacta (`v1.4.0-rc.1`) sí.
        """
        try:
            return cls.parse(text)
        except InvalidVersionError:
            return None

    def __str__(self) -> str:
        base = f"v{self.major}.{self.minor}.{self.patch}"
        return base if self.rc is None else f"{base}-rc.{self.rc}"


@dataclass(frozen=True)
class ReleaseManifest:
    version: ReleaseVersion
    published_at: datetime
    url: str
    sha256: str
    size: int
    min_version: ReleaseVersion
    min_version_from: datetime
    notes: str
    # Carpeta a la que se mudó el servidor de actualizaciones, si se mudó. SAVI
    # solo la adopta después de leer ahí un manifiesto con firma válida.
    server_url: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> ReleaseManifest:
        try:
            version = ReleaseVersion.parse(_text(data, "version"))
            min_version = ReleaseVersion.parse(_text(data, "min_version"))
        except InvalidVersionError as exc:
            raise InvalidManifestError(f"Versión inválida en el manifiesto: {exc.text}") from exc
        if min_version > version:
            raise InvalidManifestError("min_version es mayor que version.")

        url = _text(data, "url")
        parts = urlsplit(url)
        loopback = parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS
        if parts.scheme != "https" and not loopback:
            raise InvalidManifestError("La URL del instalador no usa HTTPS.")

        sha256 = _text(data, "sha256").lower()
        if _SHA256.match(sha256) is None:
            raise InvalidManifestError("sha256 no es un hash SHA-256 en hexadecimal.")

        size = data.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise InvalidManifestError("size tiene que ser un entero positivo.")

        notes = data.get("notes", "")
        if not isinstance(notes, str):
            raise InvalidManifestError("notes tiene que ser texto.")

        server_url = data.get("update_url")
        if server_url is not None:
            if not isinstance(server_url, str):
                raise InvalidManifestError("update_url tiene que ser texto.")
            server_url = normalize_server_url(server_url)

        return cls(
            version=version,
            published_at=_instant(data, "published_at"),
            url=url,
            sha256=sha256,
            size=size,
            min_version=min_version,
            min_version_from=_instant(data, "min_version_from"),
            notes=notes[:NOTES_MAX_CHARS],
            server_url=server_url,
        )


class UpdateState(StrEnum):
    UP_TO_DATE = "up_to_date"
    RECOMMENDED = "recommended"
    # Obligatoria, todavía dentro del plazo de `min_version_from`.
    REQUIRED = "required"
    # Obligatoria y con el plazo vencido: la interfaz se bloquea.
    BLOCKED = "blocked"


@dataclass(frozen=True)
class UpdateDecision:
    state: UpdateState
    current: ReleaseVersion
    manifest: ReleaseManifest | None = None

    @property
    def deadline(self) -> datetime | None:
        if self.state is UpdateState.REQUIRED and self.manifest is not None:
            return self.manifest.min_version_from
        return None


def decide(current: ReleaseVersion, manifest: ReleaseManifest, now: datetime) -> UpdateDecision:
    """Qué mostrarle a esta instalación frente al manifiesto publicado.

    Nunca se ofrece bajar de versión, aunque el manifiesto lo diga: una
    versión menor que la instalada se trata como "al día".
    """
    if manifest.version <= current:
        return UpdateDecision(UpdateState.UP_TO_DATE, current)
    if current < manifest.min_version:
        state = UpdateState.BLOCKED if now >= manifest.min_version_from else UpdateState.REQUIRED
        return UpdateDecision(state, current, manifest)
    return UpdateDecision(UpdateState.RECOMMENDED, current, manifest)


def _text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidManifestError(f"Falta {key} en el manifiesto.")
    return value.strip()


def _instant(data: Mapping[str, object], key: str) -> datetime:
    raw = _text(data, key)
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise InvalidManifestError(f"{key} no es una fecha ISO 8601.") from exc
    if value.tzinfo is None:
        raise InvalidManifestError(f"{key} no indica la zona horaria.")
    return value
