"""Cifrado con contraseña del archivo de export/import.

Distinto del `FernetCredentialCipher` (que usa `ERP_CREDENTIALS_KEY`,
aleatoria por instalación): acá la clave se deriva de una contraseña
que el admin define al exportar, para que otra instalación pueda
descifrar el archivo sin conocer secretos internos de esta máquina.
"""
from __future__ import annotations

import pytest

from app.modules.erp_databases.domain.exceptions import InvalidExportPassphraseError
from app.modules.erp_databases.infrastructure.security.export_cipher import (
    decrypt_with_passphrase,
    encrypt_with_passphrase,
)


def test_round_trips_with_the_correct_passphrase() -> None:
    blob = encrypt_with_passphrase("contenido secreto", "una-contraseña-fuerte")

    assert decrypt_with_passphrase(blob, "una-contraseña-fuerte") == "contenido secreto"


def test_wrong_passphrase_raises_instead_of_leaking_ciphertext() -> None:
    blob = encrypt_with_passphrase("contenido secreto", "correcta")

    with pytest.raises(InvalidExportPassphraseError):
        decrypt_with_passphrase(blob, "incorrecta")


def test_corrupted_blob_raises_the_same_domain_error() -> None:
    with pytest.raises(InvalidExportPassphraseError):
        decrypt_with_passphrase("esto-no-es-un-blob-valido", "cualquiera")


def test_same_passphrase_produces_different_ciphertext_each_time() -> None:
    """El salt aleatorio evita que la misma contraseña siempre cifre
    igual — dos exports del mismo admin no deberían ser comparables
    byte a byte."""
    first = encrypt_with_passphrase("contenido", "misma-contraseña")
    second = encrypt_with_passphrase("contenido", "misma-contraseña")

    assert first != second
    assert decrypt_with_passphrase(first, "misma-contraseña") == "contenido"
    assert decrypt_with_passphrase(second, "misma-contraseña") == "contenido"
