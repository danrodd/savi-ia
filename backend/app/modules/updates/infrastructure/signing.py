"""Verificación de lo que llega del servidor de actualizaciones.

Dos controles, en este orden, y ninguno se saltea:

1. **Firma Ed25519 del manifiesto** con la clave pública de SEO incrustada en
   SAVI. Quien tome el servidor puede cambiar archivos, pero no firmarlos:
   la clave privada nunca está ahí.
2. **SHA-256 y tamaño del instalador** contra el manifiesto ya verificado.
   Sin firma Authenticode (D3), este hash es lo que garantiza que se ejecuta
   el instalador que publicó SEO.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path
from typing import cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.modules.updates.domain.exceptions import (
    InstallerIntegrityError,
    InvalidManifestError,
    UntrustedManifestError,
)
from app.modules.updates.domain.value_objects import ReleaseManifest

# Tope del manifiesto: son unos cientos de bytes. Más que esto no es un
# manifiesto y no se intenta parsear.
MANIFEST_MAX_BYTES = 64 * 1024
_CHUNK = 1024 * 1024


def load_public_key(encoded: str) -> Ed25519PublicKey | None:
    """La clave pública en base64 (32 bytes crudos), o `None` si no hay."""
    if not encoded.strip():
        return None
    try:
        raw = base64.b64decode(encoded.strip(), validate=True)
        return Ed25519PublicKey.from_public_bytes(raw)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("La clave pública de actualizaciones no es Ed25519 en base64.") from exc


def verify_manifest(
    public_key: Ed25519PublicKey, manifest_bytes: bytes, signature: bytes
) -> ReleaseManifest:
    """Verifica la firma sobre los bytes exactos y recién ahí los interpreta.

    `signature` es el contenido del `.sig`: la firma en base64.
    """
    if len(manifest_bytes) > MANIFEST_MAX_BYTES:
        raise InvalidManifestError("El manifiesto es demasiado grande.")
    try:
        raw_signature = base64.b64decode(signature.strip(), validate=True)
        public_key.verify(raw_signature, manifest_bytes)
    except (binascii.Error, ValueError, InvalidSignature) as exc:
        raise UntrustedManifestError("La firma del manifiesto no es válida.") from exc

    try:
        data: object = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidManifestError("El manifiesto no es JSON válido.") from exc
    if not isinstance(data, dict):
        raise InvalidManifestError("El manifiesto no es un objeto JSON.")
    return ReleaseManifest.from_mapping(cast(dict[str, object], data))


def verify_installer(path: Path, manifest: ReleaseManifest) -> None:
    size = path.stat().st_size
    if size != manifest.size:
        raise InstallerIntegrityError(
            f"El instalador mide {size} bytes y el manifiesto dice {manifest.size}."
        )
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    if digest.hexdigest() != manifest.sha256:
        raise InstallerIntegrityError("El SHA-256 del instalador no coincide con el manifiesto.")
