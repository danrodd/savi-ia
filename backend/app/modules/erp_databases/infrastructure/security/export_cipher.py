"""Cifrado del archivo de export/import de bases del ERP.

Cada instalación de SAVI cifra las contraseñas con su propia
`ERP_CREDENTIALS_KEY`, aleatoria por instalación (D4) — así que no se
puede copiar la fila cifrada de una máquina a otra: la destino no tiene
la clave para descifrarla.

Para que varios agentes de un call center compartan la misma
configuración, el export re-cifra el contenido con una clave derivada
de una CONTRASEÑA que el admin define al exportar — no la
`ERP_CREDENTIALS_KEY` de la instalación, que nunca sale del proceso.
Quien importa tiene que conocer esa misma contraseña; sin ella, el
archivo es inútil.

PBKDF2-HMAC-SHA256 deriva una clave Fernet a partir de la contraseña.
El salt viaja con el blob — no es secreto, solo evita que la misma
contraseña produzca siempre la misma clave. 600.000 iteraciones sigue
la recomendación de OWASP (2023) para PBKDF2-HMAC-SHA256; es una
operación de admin, no de cada request, así que el costo (~cientos de
ms) no importa.
"""
from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.modules.erp_databases.domain.exceptions import InvalidExportPassphraseError

_SALT_BYTES = 16
_ITERATIONS = 600_000


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_ITERATIONS
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def encrypt_with_passphrase(plaintext: str, passphrase: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    token = Fernet(_derive_key(passphrase, salt)).encrypt(plaintext.encode("utf-8"))
    return f"{base64.urlsafe_b64encode(salt).decode('ascii')}:{token.decode('ascii')}"


def decrypt_with_passphrase(blob: str, passphrase: str) -> str:
    """Levanta `InvalidExportPassphraseError` (422) ante cualquier fallo:
    contraseña incorrecta, blob corrompido o mal formado. Nunca deja
    escapar el detalle criptográfico — quien está importando solo
    necesita saber que tiene que revisar la contraseña o el archivo."""
    try:
        salt_b64, token = blob.split(":", 1)
        salt = base64.urlsafe_b64decode(salt_b64)
        plaintext = Fernet(_derive_key(passphrase, salt)).decrypt(token.encode("ascii"))
        return plaintext.decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as e:
        raise InvalidExportPassphraseError(
            "No se pudo leer el archivo: la contraseña de exportación es "
            "incorrecta, o el archivo está dañado o no es de SAVI."
        ) from e
