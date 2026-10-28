"""Cambio de servidor anunciado por el manifiesto firmado (`update_url`)."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.modules.updates.domain.exceptions import InvalidManifestError
from app.modules.updates.domain.value_objects import ReleaseManifest
from app.modules.updates.infrastructure.http_source import HttpManifestSource
from app.modules.updates.infrastructure.server_pointer import FileServerPointer

OLD = "https://old.example.com/savi"
NEW = "https://new.example.com/savi"
INSTALLER = b"MZ" + bytes(64)


def _data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "version": "v1.4.0",
        "published_at": "2026-11-02T15:00:00Z",
        "url": f"{OLD}/releases/SAVI-Setup-v1.4.0.exe",
        "sha256": hashlib.sha256(INSTALLER).hexdigest(),
        "size": len(INSTALLER),
        "min_version": "v1.3.1",
        "min_version_from": "2026-11-05T15:00:00Z",
        "notes": "",
    }
    data.update(overrides)
    return data


def _signed(key: Ed25519PrivateKey, base: str, **overrides: object) -> dict[str, bytes]:
    payload = json.dumps(_data(**overrides)).encode()
    return {
        f"{base}/stable.json": payload,
        f"{base}/stable.json.sig": base64.b64encode(key.sign(payload)),
    }


def _source(
    key: Ed25519PrivateKey, files: dict[str, bytes], pointer: FileServerPointer | None
) -> HttpManifestSource:
    def handler(request: httpx.Request) -> httpx.Response:
        body = files.get(str(request.url))
        return httpx.Response(404) if body is None else httpx.Response(200, content=body)

    return HttpManifestSource(
        base_url=OLD,
        channel="stable",
        public_keys=[key.public_key()],
        pointer=pointer,
        transport=httpx.MockTransport(handler),
    )


@pytest.fixture
def key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def test_the_manifest_reads_the_new_server() -> None:
    manifest = ReleaseManifest.from_mapping(_data(update_url=NEW + "/"))
    assert manifest.server_url == NEW


def test_a_manifest_without_the_field_keeps_the_server() -> None:
    assert ReleaseManifest.from_mapping(_data()).server_url is None


@pytest.mark.parametrize("bad", ["http://new.example.com/savi", "ftp://x/y", "no es una url", 5])
def test_a_new_server_must_be_https(bad: object) -> None:
    with pytest.raises(InvalidManifestError):
        ReleaseManifest.from_mapping(_data(update_url=bad))


async def test_it_moves_when_the_new_server_answers_with_a_valid_manifest(
    key: Ed25519PrivateKey, tmp_path: Path
) -> None:
    pointer = FileServerPointer(tmp_path / "server.json")
    files = _signed(key, OLD, update_url=NEW) | _signed(key, NEW, version="v1.4.1")

    manifest = await _source(key, files, pointer).fetch()

    assert str(manifest.version) == "v1.4.1"
    assert pointer.read() == NEW


async def test_it_does_not_move_when_the_new_server_is_not_ready(
    key: Ed25519PrivateKey, tmp_path: Path
) -> None:
    pointer = FileServerPointer(tmp_path / "server.json")
    files = _signed(key, OLD, update_url=NEW)

    manifest = await _source(key, files, pointer).fetch()

    assert str(manifest.version) == "v1.4.0"
    assert pointer.read() is None


async def test_it_does_not_move_when_the_new_server_is_signed_by_someone_else(
    key: Ed25519PrivateKey, tmp_path: Path
) -> None:
    pointer = FileServerPointer(tmp_path / "server.json")
    stranger = Ed25519PrivateKey.generate()
    files = _signed(key, OLD, update_url=NEW) | _signed(stranger, NEW, version="v9.9.9")

    manifest = await _source(key, files, pointer).fetch()

    assert str(manifest.version) == "v1.4.0"
    assert pointer.read() is None


async def test_after_moving_it_keeps_asking_the_new_server(
    key: Ed25519PrivateKey, tmp_path: Path
) -> None:
    pointer = FileServerPointer(tmp_path / "server.json")
    files = _signed(key, OLD, update_url=NEW) | _signed(key, NEW, version="v1.4.1")
    source = _source(key, files, pointer)

    await source.fetch()
    del files[f"{OLD}/stable.json"]

    assert str((await source.fetch()).version) == "v1.4.1"


def test_a_broken_pointer_file_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "server.json"
    path.write_text("{no es json", encoding="utf-8")
    assert FileServerPointer(path).read() is None

    path.write_text(json.dumps({"url": "http://inseguro.example.com"}), encoding="utf-8")
    assert FileServerPointer(path).read() is None
