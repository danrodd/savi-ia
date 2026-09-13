"""Tests del cifrado de credenciales de conexión al ERP.

Lo que se protege acá:

- El cifrado es reversible (simétrico), porque la contraseña hace falta
  en claro para armar la URL de conexión.
- Una clave equivocada NO revienta la aplicación: se traduce a
  `CredentialDecryptError`, que el repositorio convierte en
  `credentials_unreadable`.
- El texto cifrado no contiene la contraseña en claro.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.modules.erp_databases.domain.interfaces import CredentialDecryptError
from app.modules.erp_databases.infrastructure.security import (
    FernetCredentialCipher,
    InvalidCredentialsKeyError,
)

_KEY_A = Fernet.generate_key().decode()
_KEY_B = Fernet.generate_key().decode()


def test_encrypt_decrypt_round_trip() -> None:
    cipher = FernetCredentialCipher(_KEY_A)
    assert cipher.decrypt(cipher.encrypt("s3cr3t-p4ss")) == "s3cr3t-p4ss"


def test_ciphertext_does_not_contain_plaintext() -> None:
    cipher = FernetCredentialCipher(_KEY_A)
    assert "s3cr3t-p4ss" not in cipher.encrypt("s3cr3t-p4ss")


def test_encrypt_is_not_deterministic() -> None:
    """Dos cifrados del mismo valor difieren (IV aleatorio).

    Si fueran iguales, alguien con acceso de lectura a la tabla podría
    deducir que dos clientes comparten contraseña sin descifrar nada.
    """
    cipher = FernetCredentialCipher(_KEY_A)
    assert cipher.encrypt("misma") != cipher.encrypt("misma")


def test_password_with_special_characters_round_trips() -> None:
    # Los caracteres que romperían la URL de conexión si no se escaparan.
    weird = "p@ss:w/rd#con espacios+y=ñ"
    cipher = FernetCredentialCipher(_KEY_A)
    assert cipher.decrypt(cipher.encrypt(weird)) == weird


def test_wrong_key_raises_domain_error_not_crypto_error() -> None:
    """La clave equivocada da la excepción del dominio, no una de cripto.

    Es lo que permite que el repositorio la atrape y marque la base como
    ilegible en vez de tumbar el arranque.
    """
    token = FernetCredentialCipher(_KEY_A).encrypt("secreto")
    with pytest.raises(CredentialDecryptError):
        FernetCredentialCipher(_KEY_B).decrypt(token)


def test_tampered_ciphertext_is_rejected() -> None:
    """Fernet autentica: un token modificado falla en vez de devolver
    basura. Es la razón de elegirlo sobre un AES-CBC pelado."""
    token = FernetCredentialCipher(_KEY_A).encrypt("secreto")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(CredentialDecryptError):
        FernetCredentialCipher(_KEY_A).decrypt(tampered)


def test_old_key_still_decrypts_during_rotation() -> None:
    """Rotación sin downtime: se cifra con la nueva y se sigue leyendo lo
    guardado con la vieja."""
    old_token = FernetCredentialCipher(_KEY_A).encrypt("secreto")
    rotated = FernetCredentialCipher(_KEY_B, old_keys=[_KEY_A])

    assert rotated.decrypt(old_token) == "secreto"
    # Y lo nuevo se cifra con la clave nueva: la vieja ya no lo lee.
    with pytest.raises(CredentialDecryptError):
        FernetCredentialCipher(_KEY_A).decrypt(rotated.encrypt("secreto"))


@pytest.mark.parametrize("bad_key", ["", "   ", "no-es-base64", "YWJj"])
def test_invalid_key_fails_at_construction(bad_key: str) -> None:
    """Una clave inválida SÍ es fatal, a diferencia de un descifrado que
    falla: sin clave no se puede leer ni guardar nada, y arrancar así solo
    posterga el error hasta el primer chat."""
    with pytest.raises(InvalidCredentialsKeyError):
        FernetCredentialCipher(bad_key)
