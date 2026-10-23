"""Lectura del servidor de actualizaciones, con un servidor simulado (sin red)."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.modules.updates.domain.exceptions import (
    InstallerIntegrityError,
    InvalidManifestError,
    UntrustedManifestError,
    UpdateError,
)
from app.modules.updates.domain.value_objects import ReleaseManifest, ReleaseVersion
from app.modules.updates.infrastructure.http_source import (
    HttpInstallerDownloader,
    HttpManifestSource,
)

BASE = "https://updates.example.com/savi"
INSTALLER = b"MZ" + bytes(range(256)) * 64


def _manifest_bytes(**overrides: object) -> bytes:
    data: dict[str, object] = {
        "version": "v1.4.0",
        "published_at": "2026-11-02T15:00:00Z",
        "url": f"{BASE}/releases/SAVI-Setup-v1.4.0.exe",
        "sha256": hashlib.sha256(INSTALLER).hexdigest(),
        "size": len(INSTALLER),
        "min_version": "v1.3.1",
        "min_version_from": "2026-11-05T15:00:00Z",
        "notes": "",
    }
    data.update(overrides)
    return json.dumps(data).encode()


def _server(files: dict[str, bytes]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = files.get(str(request.url))
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, content=body)

    return httpx.MockTransport(handler)


@pytest.fixture
def key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def _source(key: Ed25519PrivateKey, files: dict[str, bytes]) -> HttpManifestSource:
    return HttpManifestSource(
        base_url=BASE + "/",
        channel="stable",
        public_keys=[key.public_key()],
        transport=_server(files),
    )


async def test_fetches_and_verifies_the_channel_manifest(key: Ed25519PrivateKey) -> None:
    payload = _manifest_bytes()
    files = {
        f"{BASE}/stable.json": payload,
        f"{BASE}/stable.json.sig": base64.b64encode(key.sign(payload)),
    }
    manifest = await _source(key, files).fetch()
    assert manifest.version == ReleaseVersion(1, 4, 0)


async def test_missing_signature_is_an_update_error(key: Ed25519PrivateKey) -> None:
    files = {f"{BASE}/stable.json": _manifest_bytes()}
    with pytest.raises(UpdateError):
        await _source(key, files).fetch()


async def test_signature_for_other_content_is_rejected(key: Ed25519PrivateKey) -> None:
    files = {
        f"{BASE}/stable.json": _manifest_bytes(version="v9.9.9"),
        f"{BASE}/stable.json.sig": base64.b64encode(key.sign(_manifest_bytes())),
    }
    with pytest.raises(UntrustedManifestError):
        await _source(key, files).fetch()


async def test_network_failure_is_an_update_error(key: Ed25519PrivateKey) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    source = HttpManifestSource(
        base_url=BASE,
        channel="stable",
        public_keys=[key.public_key()],
        transport=httpx.MockTransport(fail),
    )
    with pytest.raises(UpdateError):
        await source.fetch()


def _files(folder: Path, pattern: str = "*") -> list[Path]:
    return list(folder.glob(pattern))


def _write(path: Path, content: bytes) -> None:
    path.write_bytes(content)


def _manifest(**overrides: object) -> ReleaseManifest:
    return ReleaseManifest.from_mapping(json.loads(_manifest_bytes(**overrides)))


async def test_download_writes_the_verified_installer(tmp_path: Path) -> None:
    stale = tmp_path / "SAVI-Setup-v1.3.9.exe"
    _write(stale, b"viejo")
    progress: list[int] = []
    downloader = HttpInstallerDownloader(
        target_dir=tmp_path,
        transport=_server({f"{BASE}/releases/SAVI-Setup-v1.4.0.exe": INSTALLER}),
    )

    path = await downloader.download(_manifest(), progress.append)

    assert _files(tmp_path) == [path]
    assert progress[-1] == len(INSTALLER)
    assert not _files(tmp_path, "*.partial")


async def test_download_with_other_bytes_is_rejected_and_removed(tmp_path: Path) -> None:
    tampered = INSTALLER[:-1] + b"\x00"
    downloader = HttpInstallerDownloader(
        target_dir=tmp_path,
        transport=_server({f"{BASE}/releases/SAVI-Setup-v1.4.0.exe": tampered}),
    )
    with pytest.raises(InstallerIntegrityError):
        await downloader.download(_manifest(), lambda _: None)
    assert _files(tmp_path) == []


async def test_download_larger_than_the_manifest_is_cut(tmp_path: Path) -> None:
    downloader = HttpInstallerDownloader(
        target_dir=tmp_path,
        transport=_server({f"{BASE}/releases/SAVI-Setup-v1.4.0.exe": INSTALLER + b"extra"}),
    )
    with pytest.raises(InstallerIntegrityError):
        await downloader.download(_manifest(), lambda _: None)
    assert _files(tmp_path) == []


async def test_missing_installer_is_an_update_error(tmp_path: Path) -> None:
    downloader = HttpInstallerDownloader(target_dir=tmp_path, transport=_server({}))
    with pytest.raises(UpdateError):
        await downloader.download(_manifest(), lambda _: None)


async def test_stable_channel_rejects_a_candidate_even_if_signed(key: Ed25519PrivateKey) -> None:
    payload = _manifest_bytes(
        version="v1.4.0-rc.1", url=f"{BASE}/releases/SAVI-Setup-v1.4.0-rc.1.exe"
    )
    files = {
        f"{BASE}/stable.json": payload,
        f"{BASE}/stable.json.sig": base64.b64encode(key.sign(payload)),
    }
    with pytest.raises(InvalidManifestError, match="candidatas"):
        await _source(key, files).fetch()


async def test_beta_channel_accepts_a_candidate(key: Ed25519PrivateKey) -> None:
    payload = _manifest_bytes(
        version="v1.4.0-rc.1", url=f"{BASE}/releases/SAVI-Setup-v1.4.0-rc.1.exe"
    )
    files = {
        f"{BASE}/beta.json": payload,
        f"{BASE}/beta.json.sig": base64.b64encode(key.sign(payload)),
    }
    source = HttpManifestSource(
        base_url=BASE, channel="beta", public_keys=[key.public_key()], transport=_server(files)
    )

    manifest = await source.fetch()

    assert manifest.version == ReleaseVersion(1, 4, 0, 1)
