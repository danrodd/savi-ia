"""Puerto de cifrado simétrico para credenciales de conexión.

**Simétrico, no hashing.** La contraseña de conexión al ERP tiene que
poder recuperarse en claro para armar la URL. Un `bcrypt`/`argon2` —lo
correcto para contraseñas de usuario, y lo que usa el módulo `auth` para
verificar el login— acá no sirve: no se puede deshacer.

Es un puerto y no una llamada directa a Fernet para poder testear los
casos de uso con un cipher falso, y para poder cambiar mañana a DPAPI de
Windows o a un gestor de secretos sin tocar `application/`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class CredentialDecryptError(Exception):
    """El texto cifrado no se pudo descifrar con la clave actual.

    Ocurre cuando `ERP_CREDENTIALS_KEY` cambió o se perdió — un `.env`
    restaurado de un backup distinto, una reinstalación.

    **No debe propagarse hasta tumbar la aplicación.** El repositorio la
    traduce a `credentials_unreadable=True` en la entidad: esa base queda
    inutilizable hasta re-ingresar la contraseña, y el resto de SAVI
    arranca normal.
    """


class CredentialCipher(ABC):
    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        """Devuelve el texto cifrado, listo para persistir en una columna
        de texto."""

    @abstractmethod
    def decrypt(self, ciphertext: str) -> str:
        """Devuelve el texto en claro.

        Levanta `CredentialDecryptError` si la clave no corresponde o el
        token está corrupto.
        """
