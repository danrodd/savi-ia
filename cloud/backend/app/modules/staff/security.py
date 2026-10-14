"""Primitivas de seguridad del staff: contraseñas, TOTP, cifrado de secretos y JWT.

Todo lo que depende de tiempo recibe el reloj inyectado, así los tests lo controlan.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime, timedelta
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken

from app.modules.staff.domain import InvalidSessionToken, WeakPassword
from app.shared.clock import Clock

TokenPurpose = Literal["access", "refresh", "mfa", "mfa_setup"]

ISSUER = "savi-cloud-console"
ACCESS_TTL = timedelta(minutes=15)
MFA_TTL = timedelta(minutes=5)
MFA_SETUP_TTL = timedelta(minutes=10)
REFRESH_TTL = timedelta(hours=8)

TOTP_PERIOD = 30
TOTP_DIGITS = 6
MIN_PASSWORD_LENGTH = 12

# Lista local de contraseñas comunes (en minúsculas, ya con el largo mínimo). No pretende ser
# exhaustiva: junto con las reglas de variedad, bloquea las que un atacante prueba primero.
_COMMON_PASSWORDS = frozenset(
    {
        "123456789012",
        "1234567890123",
        "password1234",
        "password12345",
        "passw0rd1234",
        "contrasena123",
        "contrasena1234",
        "contraseña123",
        "qwertyuiop12",
        "qwertyuiop123",
        "qwerty123456",
        "abc123456789",
        "administrator",
        "administrador",
        "welcome12345",
        "bienvenido123",
        "letmein12345",
        "iloveyou1234",
        "changeme1234",
        "cambiame1234",
        "savicloud123",
        "savicloud1234",
        "seogroup1234",
        "seogroup12345",
        "colombia12345",
        "123456789abc",
        "1q2w3e4r5t6y",
        "1qaz2wsx3edc",
    }
)


def validate_password_policy(password: str, *, email: str | None = None) -> None:
    """Mínimo 12 caracteres, fuera de la lista de comunes y con algo de variedad."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")
    if len(password) > 256:
        raise WeakPassword("La contraseña admite hasta 256 caracteres.")
    lowered = password.lower()
    if lowered in _COMMON_PASSWORDS:
        raise WeakPassword("Esa contraseña es demasiado común.")
    if len(set(lowered)) < 5:
        raise WeakPassword("La contraseña tiene muy poca variedad de caracteres.")
    if email:
        local = email.split("@", 1)[0].lower()
        if len(local) >= 4 and local in lowered:
            raise WeakPassword("La contraseña no debe contener tu correo.")


def generate_temporary_password() -> str:
    """Contraseña temporal aleatoria (≥ 12 caracteres, cumple la política)."""
    return secrets.token_urlsafe(18)


# ------------------------------------------------------------------ TOTP (RFC 6238)


def generate_totp_secret() -> str:
    """Secreto de 160 bits en base32 (el formato que esperan las apps de autenticación)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def totp_code(secret_b32: str, step: int) -> str:
    key = base64.b32decode(secret_b32, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**TOTP_DIGITS).zfill(TOTP_DIGITS)


def verify_totp(secret_b32: str, code: str, now: datetime, last_step: int) -> int | None:
    """Paso (`int`) del código si es válido en la ventana ±1 y **no** se usó antes.

    Un código ya consumido (o anterior al último paso aceptado) devuelve `None`.
    """
    clean = code.strip().replace(" ", "")
    if len(clean) != TOTP_DIGITS or not clean.isdigit():
        return None
    current = int(now.timestamp() // TOTP_PERIOD)
    matched: int | None = None
    for step in (current - 1, current, current + 1):
        # Se recorren todos (sin cortar) para no filtrar por tiempo cuál coincidió.
        if hmac.compare_digest(totp_code(secret_b32, step), clean):
            matched = step
    if matched is None or matched <= last_step:
        return None
    return matched


def otpauth_uri(secret_b32: str, email: str, issuer: str = "SAVI Cloud") -> str:
    label = quote(f"{issuer}:{email}", safe="")
    return (
        f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer, safe='')}"
        f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD}"
    )


# ------------------------------------------------------------------ Servicio


class StaffSecurity:
    """Contraseñas (argon2id), secretos TOTP cifrados (Fernet) y JWT firmados (HS256).

    `secret` es la única semilla configurada; de ella se derivan claves independientes
    para firmar y para cifrar, de modo que una no sirve para la otra.
    """

    def __init__(self, secret: str, clock: Clock) -> None:
        self._clock = clock
        self._jwt_key = hashlib.sha256(b"savi-cloud:jwt:" + secret.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(
            hashlib.sha256(b"savi-cloud:totp:" + secret.encode()).digest()
        )
        self._fernet = Fernet(fernet_key)
        self._hasher = PasswordHasher()  # argon2id con los parámetros por defecto de la librería
        self._dummy_hash = self._hasher.hash("savi-cloud-dummy-password-for-timing")

    # --- contraseñas (CPU intensivo: fuera del event loop)

    async def hash_password(self, password: str) -> str:
        return await asyncio.to_thread(self._hasher.hash, password)

    async def verify_password(self, password_hash: str, password: str) -> bool:
        def _verify() -> bool:
            try:
                return self._hasher.verify(password_hash, password)
            except (VerificationError, InvalidHashError):
                return False

        return await asyncio.to_thread(_verify)

    async def dummy_verify(self, password: str) -> None:
        """Gasta lo mismo que una verificación real (email inexistente o cuenta bloqueada)."""
        await self.verify_password(self._dummy_hash, password)

    # --- secretos TOTP

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise InvalidSessionToken("El secreto TOTP no se puede leer.") from exc

    # --- JWT

    def issue(self, purpose: TokenPurpose, subject: UUID, ttl: timedelta, **claims: Any) -> str:
        now = self._clock()
        payload: dict[str, Any] = {
            "iss": ISSUER,
            "sub": str(subject),
            "purpose": purpose,
            "iat": int(now.timestamp()),
            "exp": int((now + ttl).timestamp()),
            **claims,
        }
        return jwt.encode(payload, self._jwt_key, algorithm="HS256")

    def decode(self, token: str, purpose: TokenPurpose) -> dict[str, Any]:
        """Valida firma, emisor, propósito y vencimiento (con el reloj inyectado)."""
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self._jwt_key,
                algorithms=["HS256"],
                issuer=ISSUER,
                options={
                    "verify_exp": False,
                    "verify_iat": False,
                    "require": ["exp", "sub", "purpose"],
                },
            )
        except jwt.PyJWTError as exc:
            raise InvalidSessionToken("Token inválido.") from exc
        if payload.get("purpose") != purpose:
            raise InvalidSessionToken("Token inválido.")
        if int(payload["exp"]) <= int(self._clock().timestamp()):
            raise InvalidSessionToken("El token venció.")
        return payload
