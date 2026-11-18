"""Firma del manifiesto e integridad del instalador.

Es la única barrera entre el servidor de actualizaciones y ejecutar código en
cada equipo: cualquier byte cambiado tiene que rechazarse.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.modules.updates.domain.exceptions import (
    InstallerIntegrityError,
    InvalidManifestError,
    UntrustedManifestError,
)
from app.modules.updates.domain.value_objects import ReleaseVersion
from app.modules.updates.infrastructure.signing import (
    load_public_key,
    load_public_keys,
    verify_installer,
    verify_manifest,
)

INSTALLER = b"MZ" + b"\x00" * 1024


def _manifest_bytes(**overrides: object) -> bytes:
    data: dict[str, object] = {
        "version": "v1.4.0",
        "published_at": "2026-11-02T15:00:00Z",
        "url": "https://updates.example.com/savi/releases/SAVI-Setup-v1.4.0.exe",
        "sha256": hashlib.sha256(INSTALLER).hexdigest(),
        "size": len(INSTALLER),
        "min_version": "v1.3.1",
        "min_version_from": "2026-11-05T15:00:00Z",
        "notes": "",
    }
    data.update(overrides)
    return json.dumps(data).encode()


def _sign(key: Ed25519PrivateKey, payload: bytes) -> bytes:
    return base64.b64encode(key.sign(payload))


def _public_b64(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode()


@pytest.fixture
def key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def test_signed_manifest_is_accepted(key: Ed25519PrivateKey) -> None:
    public = load_public_keys([_public_b64(key)])
    payload = _manifest_bytes()
    manifest = verify_manifest(public, payload, _sign(key, payload))
    assert manifest.version == ReleaseVersion(1, 4, 0)


def test_tampered_manifest_is_rejected(key: Ed25519PrivateKey) -> None:
    public = load_public_keys([_public_b64(key)])
    signature = _sign(key, _manifest_bytes())
    tampered = _manifest_bytes(url="https://attacker.example.com/SAVI-Setup.exe")
    with pytest.raises(UntrustedManifestError):
        verify_manifest(public, tampered, signature)


def test_manifest_signed_with_another_key_is_rejected(key: Ed25519PrivateKey) -> None:
    public = load_public_keys([_public_b64(key)])
    payload = _manifest_bytes()
    with pytest.raises(UntrustedManifestError):
        verify_manifest(public, payload, _sign(Ed25519PrivateKey.generate(), payload))


@pytest.mark.parametrize("signature", [b"", b"no es base64!", base64.b64encode(b"corta")])
def test_malformed_signature_is_rejected(key: Ed25519PrivateKey, signature: bytes) -> None:
    public = load_public_keys([_public_b64(key)])
    with pytest.raises(UntrustedManifestError):
        verify_manifest(public, _manifest_bytes(), signature)


def test_signed_but_invalid_content_is_still_rejected(key: Ed25519PrivateKey) -> None:
    public = load_public_keys([_public_b64(key)])
    payload = b"[1, 2, 3]"
    with pytest.raises(InvalidManifestError):
        verify_manifest(public, payload, _sign(key, payload))


def test_empty_public_key_disables_updates() -> None:
    assert load_public_key("") is None
    assert load_public_key("   ") is None


def test_malformed_public_key_fails_loudly() -> None:
    with pytest.raises(ValueError):
        load_public_key("no-es-una-clave")


def test_installer_matching_the_manifest_passes(key: Ed25519PrivateKey, tmp_path: Path) -> None:
    public = load_public_keys([_public_b64(key)])
    payload = _manifest_bytes()
    manifest = verify_manifest(public, payload, _sign(key, payload))
    installer = tmp_path / "SAVI-Setup-v1.4.0.exe"
    installer.write_bytes(INSTALLER)
    verify_installer(installer, manifest)


@pytest.mark.parametrize("content", [INSTALLER[:-1] + b"\x01", INSTALLER + b"\x00"])
def test_installer_with_other_bytes_is_rejected(
    key: Ed25519PrivateKey, tmp_path: Path, content: bytes
) -> None:
    public = load_public_keys([_public_b64(key)])
    payload = _manifest_bytes()
    manifest = verify_manifest(public, payload, _sign(key, payload))
    installer = tmp_path / "SAVI-Setup-v1.4.0.exe"
    installer.write_bytes(content)
    with pytest.raises(InstallerIntegrityError):
        verify_installer(installer, manifest)


def test_manifest_signed_by_the_backup_key_is_accepted(key: Ed25519PrivateKey) -> None:
    backup = Ed25519PrivateKey.generate()
    public = load_public_keys([_public_b64(key), _public_b64(backup)])
    payload = _manifest_bytes()
    assert verify_manifest(public, payload, _sign(backup, payload)).version == ReleaseVersion(
        1, 4, 0
    )
    assert verify_manifest(public, payload, _sign(key, payload)).version == ReleaseVersion(1, 4, 0)


def test_manifest_signed_by_none_of_the_keys_is_rejected(key: Ed25519PrivateKey) -> None:
    public = load_public_keys([_public_b64(key), _public_b64(Ed25519PrivateKey.generate())])
    payload = _manifest_bytes()
    with pytest.raises(UntrustedManifestError):
        verify_manifest(public, payload, _sign(Ed25519PrivateKey.generate(), payload))


def test_no_keys_trusts_nothing(key: Ed25519PrivateKey) -> None:
    payload = _manifest_bytes()
    with pytest.raises(UntrustedManifestError):
        verify_manifest((), payload, _sign(key, payload))


def test_blank_and_malformed_keys_are_skipped_without_disabling_the_others(
    key: Ed25519PrivateKey,
) -> None:
    assert load_public_keys(["", "  "]) == ()
    assert load_public_keys(["no-es-una-clave"]) == ()
    public = load_public_keys(["no-es-una-clave", _public_b64(key)])
    payload = _manifest_bytes()
    assert verify_manifest(public, payload, _sign(key, payload)).version == ReleaseVersion(1, 4, 0)


def test_shipped_keys_are_two_distinct_valid_ed25519_keys() -> None:
    from app.modules.updates.infrastructure.trust import UPDATE_PUBLIC_KEYS

    assert len(UPDATE_PUBLIC_KEYS) == 2
    assert len(set(UPDATE_PUBLIC_KEYS)) == 2
    assert len(load_public_keys(UPDATE_PUBLIC_KEYS)) == 2
