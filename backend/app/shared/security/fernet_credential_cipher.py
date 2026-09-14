"""Impl `CredentialCipher` con Fernet.

Fernet = AES-128-CBC (confidencialidad) + HMAC-SHA256 (integridad), con
IV aleatorio y timestamp, empaquetado en base64 urlsafe. El token entra
tal cual en una columna `Text`.

Se elige Fernet y no AES a mano por dos razones:

- **Autentica.** Un AES-CBC sin HMAC permite modificar el ciphertext sin
  que se note al descifrar. Fernet lo detecta y falla.
- **No hay que escribir criptografía propia.** El modo, el padding y el
  IV ya vienen resueltos y auditados.

`cryptography` ya es dependencia del proyecto: la usa PyJWT para firmar.

Rotación de clave: `MultiFernet` cifra siempre con la primera clave y
descifra probando todas. Con `ERP_CREDENTIALS_KEY_OLD` se puede rotar
sin downtime — cifrar con la nueva, seguir leyendo lo viejo, re-cifrar y
borrar la vieja.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.shared.security.credential_cipher import CredentialCipher, CredentialDecryptError


class InvalidCredentialsKeyError(ValueError):
    """`ERP_CREDENTIALS_KEY` falta o no es una clave Fernet válida.

    Esta **sí** es fatal al arranque, a diferencia de un descifrado que
    falla: sin clave no se puede ni leer ni guardar ninguna credencial, y
    arrancar en ese estado solo posterga el error hasta el primer chat.
    """


def _build(keys: list[str]) -> MultiFernet:
    if not keys:
        raise InvalidCredentialsKeyError(
            "ERP_CREDENTIALS_KEY es obligatoria. Generá una con: "
            "python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError) as e:
        raise InvalidCredentialsKeyError(
            "ERP_CREDENTIALS_KEY no es una clave Fernet válida (se esperan "
            f"32 bytes en base64 urlsafe, 44 caracteres): {e}"
        ) from e


class FernetCredentialCipher(CredentialCipher):
    def __init__(self, key: str, *, old_keys: list[str] | None = None) -> None:
        # Orden importante: la primera es con la que se cifra. Las
        # antiguas solo participan del descifrado.
        keys = [k for k in [key, *(old_keys or [])] if k and k.strip()]
        self._fernet = _build(keys)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError) as e:
            # Traducción deliberada a la excepción del dominio: el
            # repositorio la convierte en `credentials_unreadable` y la
            # aplicación sigue funcionando. Ver el docstring de
            # `CredentialDecryptError`.
            raise CredentialDecryptError(
                "No se pudo descifrar la credencial con la clave actual. "
                "Es probable que ERP_CREDENTIALS_KEY haya cambiado."
            ) from e
