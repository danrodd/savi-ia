"""Lectura del servidor de actualizaciones, con un servidor simulado (sin red)."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import AsyncIterator
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


# ------------------------------------------------------------ descarga que se retoma

URL = f"{BASE}/releases/SAVI-Setup-v1.4.0.exe"
HALF = len(INSTALLER) // 2
PARTIAL = "SAVI-Setup-v1.4.0.exe.partial"
META = "SAVI-Setup-v1.4.0.exe.partial.json"


class _CutStream(httpx.AsyncByteStream):
    """Entrega `sent` y después corta la conexión."""

    def __init__(self, sent: bytes) -> None:
        self._sent = sent

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._sent
        raise httpx.ReadError("conexión cortada")


class _RangeServer:
    """Un servidor que respeta `Range`, con fallas programables."""

    def __init__(self, *, cuts: int = 0, honor_range: bool = True, body: bytes = INSTALLER) -> None:
        self.cuts = cuts
        self.honor_range = honor_range
        self.body = body
        self.ranges: list[str | None] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        header = request.headers.get("Range")
        self.ranges.append(header)
        start = 0
        if header and self.honor_range:
            start = int(header.removeprefix("bytes=").rstrip("-"))
            if start >= len(self.body):
                return httpx.Response(416)
        rest = self.body[start:]
        if self.cuts > 0:
            self.cuts -= 1
            return self._response(start, stream=_CutStream(rest[: len(rest) // 2]))
        return self._response(start, content=rest)

    def _response(
        self,
        start: int,
        *,
        content: bytes | None = None,
        stream: httpx.AsyncByteStream | None = None,
    ) -> httpx.Response:
        if start == 0:
            return httpx.Response(200, content=content, stream=stream)
        headers = {"Content-Range": f"bytes {start}-{len(self.body) - 1}/{len(self.body)}"}
        return httpx.Response(206, headers=headers, content=content, stream=stream)


def _downloader(tmp_path: Path, server: _RangeServer) -> HttpInstallerDownloader:
    return HttpInstallerDownloader(
        target_dir=tmp_path, transport=server.transport(), retry_delays=(0, 0, 0)
    )


def _leave_half_downloaded(folder: Path) -> None:
    identity = {"url": URL, "sha256": _manifest().sha256, "size": len(INSTALLER)}
    (folder / PARTIAL).write_bytes(INSTALLER[:HALF])
    (folder / META).write_text(json.dumps(identity), encoding="utf-8")


async def test_a_cut_download_continues_where_it_stopped(tmp_path: Path) -> None:
    server = _RangeServer(cuts=1)
    progress: list[int] = []

    path = await _downloader(tmp_path, server).download(_manifest(), progress.append)

    assert path.read_bytes() == INSTALLER
    assert server.ranges[0] is None
    assert server.ranges[1] is not None
    assert progress == sorted(progress)
    assert progress[-1] == len(INSTALLER)
    assert _files(tmp_path) == [path]


async def test_progress_starts_at_what_was_already_downloaded(tmp_path: Path) -> None:
    _leave_half_downloaded(tmp_path)
    server = _RangeServer()
    progress: list[int] = []

    path = await _downloader(tmp_path, server).download(_manifest(), progress.append)

    assert server.ranges == [f"bytes={HALF}-"]
    assert progress[0] == HALF
    assert path.read_bytes() == INSTALLER


async def test_a_server_that_ignores_the_range_sends_everything_again(tmp_path: Path) -> None:
    _leave_half_downloaded(tmp_path)
    server = _RangeServer(honor_range=False)

    path = await _downloader(tmp_path, server).download(_manifest(), lambda _: None)

    assert path.read_bytes() == INSTALLER


async def test_a_full_partial_is_verified_without_downloading(tmp_path: Path) -> None:
    _leave_half_downloaded(tmp_path)
    (tmp_path / PARTIAL).write_bytes(INSTALLER)
    server = _RangeServer()

    path = await _downloader(tmp_path, server).download(_manifest(), lambda _: None)

    assert server.ranges == []
    assert path.read_bytes() == INSTALLER


async def test_a_partial_of_another_version_is_discarded(tmp_path: Path) -> None:
    (tmp_path / PARTIAL).write_bytes(b"otra version")
    (tmp_path / META).write_text('{"sha256": "x"}', encoding="utf-8")
    (tmp_path / "SAVI-Setup-v1.3.9.exe.partial").write_bytes(b"vieja")
    server = _RangeServer()

    path = await _downloader(tmp_path, server).download(_manifest(), lambda _: None)

    assert server.ranges == [None]
    assert path.read_bytes() == INSTALLER
    assert _files(tmp_path) == [path]


async def test_a_complete_verified_installer_is_not_downloaded_again(tmp_path: Path) -> None:
    (tmp_path / "SAVI-Setup-v1.4.0.exe").write_bytes(INSTALLER)
    server = _RangeServer()
    progress: list[int] = []

    path = await _downloader(tmp_path, server).download(_manifest(), progress.append)

    assert server.ranges == []
    assert progress == [len(INSTALLER)]
    assert path.read_bytes() == INSTALLER


async def test_a_wrong_content_range_is_not_trusted(tmp_path: Path) -> None:
    _leave_half_downloaded(tmp_path)
    calls: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("Range"))
        if len(calls) == 1:
            wrong = f"bytes 0-{len(INSTALLER) - 1}/{len(INSTALLER)}"
            return httpx.Response(206, headers={"Content-Range": wrong}, content=INSTALLER)
        return httpx.Response(200, content=INSTALLER)

    downloader = HttpInstallerDownloader(
        target_dir=tmp_path, transport=httpx.MockTransport(handler), retry_delays=(0,)
    )
    path = await downloader.download(_manifest(), lambda _: None)

    assert calls == [f"bytes={HALF}-", None]
    assert path.read_bytes() == INSTALLER


async def test_a_416_with_a_stale_partial_starts_over(tmp_path: Path) -> None:
    _leave_half_downloaded(tmp_path)
    calls: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("Range"))
        if request.headers.get("Range"):
            return httpx.Response(416)
        return httpx.Response(200, content=INSTALLER)

    downloader = HttpInstallerDownloader(
        target_dir=tmp_path, transport=httpx.MockTransport(handler), retry_delays=(0,)
    )
    path = await downloader.download(_manifest(), lambda _: None)

    assert calls == [f"bytes={HALF}-", None]
    assert path.read_bytes() == INSTALLER


async def test_a_bad_hash_removes_the_partial_and_its_json(tmp_path: Path) -> None:
    server = _RangeServer(body=INSTALLER[:-1] + b"\x00")

    with pytest.raises(InstallerIntegrityError):
        await _downloader(tmp_path, server).download(_manifest(), lambda _: None)

    assert _files(tmp_path) == []


async def test_running_out_of_retries_keeps_the_partial_for_next_time(tmp_path: Path) -> None:
    server = _RangeServer(cuts=99)

    with pytest.raises(UpdateError, match="Se perdió la conexión"):
        await _downloader(tmp_path, server).download(_manifest(), lambda _: None)

    assert len(server.ranges) == 4
    assert sorted(f.name for f in _files(tmp_path)) == [PARTIAL, META]
    assert 0 < (tmp_path / PARTIAL).stat().st_size < len(INSTALLER)
