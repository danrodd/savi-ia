"""TOTP (RFC 6238) para el segundo factor de los administradores.

Sin dependencias externas: HMAC-SHA1 de la stdlib, que es lo que esperan Google Authenticator,
Microsoft Authenticator, Authy y 1Password. El secreto se muestra una sola vez al configurar
(como código QR y como texto) y vive cifrado en la base.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime
from urllib.parse import quote

PERIOD_SECONDS = 30
DIGITS = 6
# Ventana ±1 paso: tolera un reloj atrasado o adelantado hasta 30 s sin abrir la puerta a
# códigos de hace minutos.
WINDOW_STEPS = 1


def generate_secret() -> str:
    """Secreto de 160 bits en base32, el formato que cargan las aplicaciones."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def current_step(now: datetime) -> int:
    return int(now.timestamp() // PERIOD_SECONDS)


def code_at(secret: str, step: int) -> str:
    key = base64.b32decode(secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def verify(secret: str, code: str, now: datetime, last_step: int) -> int | None:
    """El paso del código si es válido y **no se usó antes**; `None` si no.

    Un código ya consumido (o de un paso anterior al último aceptado) no se acepta dos veces:
    quien ve la pantalla por encima del hombro no puede reutilizarlo.
    """
    clean = code.strip().replace(" ", "")
    if len(clean) != DIGITS or not clean.isdigit():
        return None
    step = current_step(now)
    matched: int | None = None
    for candidate in range(step - WINDOW_STEPS, step + WINDOW_STEPS + 1):
        # Se recorren todos (sin cortar) para no filtrar por tiempo cuál coincidió.
        if hmac.compare_digest(code_at(secret, candidate), clean):
            matched = candidate
    if matched is None or matched <= last_step:
        return None
    return matched


def otpauth_uri(secret: str, account: str, issuer: str) -> str:
    """La URI que codifica el QR (`otpauth://totp/...`)."""
    label = quote(f"{issuer}:{account}", safe="")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer, safe='')}"
        f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD_SECONDS}"
    )
