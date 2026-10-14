"""Generación y hash de secretos de alta entropía (tokens y secretos de instancia).

SHA-256 alcanza porque el secreto es aleatorio de 256 bits, no una contraseña humana
(decisión S4 de la Fase 2). El texto plano nunca se persiste.
"""

from __future__ import annotations

import hashlib
import secrets

ENROLLMENT_TOKEN_PREFIX = "svk_enr_"
INSTANCE_SECRET_PREFIX = "svk_ins_"

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
# 62**43 > 2**256: 43 dígitos base62 representan 32 bytes sin perder información.
_BASE62_LENGTH = 43


def _base62(data: bytes) -> str:
    number = int.from_bytes(data, "big")
    digits: list[str] = []
    while number:
        number, rem = divmod(number, 62)
        digits.append(_ALPHABET[rem])
    return "".join(reversed(digits)).rjust(_BASE62_LENGTH, _ALPHABET[0])


def generate_secret(prefix: str) -> str:
    """`prefix` + 32 bytes aleatorios en base62."""
    return prefix + _base62(secrets.token_bytes(32))


def hash_secret(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()
