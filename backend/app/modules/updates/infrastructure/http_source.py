"""Lectura del servidor de actualizaciones por HTTPS.

Sin redirecciones: el servidor sirve archivos estáticos y no tiene motivo para
redirigir. Toda falla de red se traduce a `UpdateError`, así el coordinador
la registra y SAVI sigue funcionando.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import BinaryIO

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.modules.updates.domain.exceptions import (
    InstallerIntegrityError,
    InvalidManifestError,
    UpdateError,
)
from app.modules.updates.domain.interfaces import InstallerDownloader, ManifestSource
from app.modules.updates.domain.value_objects import ReleaseManifest
from app.modules.updates.infrastructure.signing import (
    MANIFEST_MAX_BYTES,
    verify_installer,
    verify_manifest,
)

USER_AGENT = "SAVI-Update/1.0"
_MANIFEST_TIMEOUT = httpx.Timeout(15.0)
# La descarga puede tardar minutos; lo que se acota es cada lectura.
_DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, read=60.0)
# Esperas entre reintentos de una descarga cortada (segundos).
RETRY_DELAYS = (2.0, 5.0, 15.0)
LOST_CONNECTION_MESSAGE = (
    "Se perdió la conexión. Intente de nuevo: la descarga sigue desde donde quedó."
)


class HttpManifestSource(ManifestSource):
    def __init__(
        self,
        *,
        base_url: str,
        channel: str,
        public_keys: Sequence[Ed25519PublicKey],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._channel = channel
        self._manifest_url = f"{base_url.rstrip('/')}/{channel}.json"
        self._public_keys = tuple(public_keys)
        # Solo para tests: simular el servidor sin red.
        self._transport = transport

    async def fetch(self) -> ReleaseManifest:
        async with _client(_MANIFEST_TIMEOUT, self._transport) as client:
            manifest_bytes = await _get_small(client, self._manifest_url)
            signature = await _get_small(client, f"{self._manifest_url}.sig")
        manifest = verify_manifest(self._public_keys, manifest_bytes, signature)
        # Aunque la firma sea buena: una candidata nunca se ofrece en stable.
        if self._channel == "stable" and manifest.version.is_candidate:
            raise InvalidManifestError(
                f"El canal stable no admite versiones candidatas ({manifest.version})."
            )
        return manifest


class HttpInstallerDownloader(InstallerDownloader):
    """Baja el instalador y, si la conexión se corta, sigue desde donde quedó.

    Junto al `.partial` guarda un `.partial.json` con la URL, el SHA-256 y el
    tamaño del manifiesto: solo se retoma un parcial que sea de esa misma
    versión. Se pide con `Range` y se verifica lo que el servidor contesta.
    """

    def __init__(
        self,
        *,
        target_dir: Path,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_delays: Sequence[float] = RETRY_DELAYS,
    ) -> None:
        self._target_dir = target_dir
        self._transport = transport
        self._retry_delays = tuple(retry_delays)

    async def download(self, manifest: ReleaseManifest, on_progress: Callable[[int], None]) -> Path:
        self._target_dir.mkdir(parents=True, exist_ok=True)
        name = manifest.url.rsplit("/", 1)[-1]
        target = self._target_dir / name
        partial = target.with_name(f"{name}.partial")
        meta = target.with_name(f"{name}.partial.json")
        # Lo que no es de esta versión no sirve; lo de esta versión se conserva.
        for old in self._target_dir.glob("SAVI-Setup-*"):
            if old not in (target, partial, meta):
                old.unlink(missing_ok=True)

        if target.exists():
            try:
                await asyncio.to_thread(verify_installer, target, manifest)
            except InstallerIntegrityError:
                target.unlink(missing_ok=True)
            else:
                on_progress(manifest.size)
                return target
        if not _same_download(meta, manifest):
            partial.unlink(missing_ok=True)
        meta.write_text(_download_identity(manifest), encoding="utf-8")

        try:
            await self._fetch_with_retries(manifest, partial, on_progress)
            # Hashear 160 MB bloquearía el event loop.
            await asyncio.to_thread(verify_installer, partial, manifest)
        except InstallerIntegrityError:
            partial.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)
            raise
        partial.replace(target)
        meta.unlink(missing_ok=True)
        return target

    async def _fetch_with_retries(
        self, manifest: ReleaseManifest, partial: Path, on_progress: Callable[[int], None]
    ) -> None:
        delays = iter(self._retry_delays)
        while True:
            try:
                await self._fetch(manifest, partial, on_progress)
            except httpx.HTTPError as exc:
                delay = next(delays, None)
                if delay is None:
                    raise UpdateError(LOST_CONNECTION_MESSAGE) from exc
                await asyncio.sleep(delay)
            else:
                return

    async def _fetch(
        self, manifest: ReleaseManifest, partial: Path, on_progress: Callable[[int], None]
    ) -> None:
        offset = _usable_size(partial, manifest.size)
        on_progress(offset)
        if offset == manifest.size:
            return
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        async with (
            _client(_DOWNLOAD_TIMEOUT, self._transport) as client,
            client.stream("GET", manifest.url, headers=headers) as response,
        ):
            status = response.status_code
            if status == 416:
                # El servidor no acepta ese punto de partida: se baja de nuevo.
                _discard(partial)
                raise httpx.TransportError("El servidor rechazó el rango pedido.")
            if status == 200:
                # Ignoró el rango (o no había nada que retomar): llega entero.
                offset = 0
            elif status == 206 and offset:
                expected = f"bytes {offset}-{manifest.size - 1}/{manifest.size}"
                if response.headers.get("Content-Range") != expected:
                    _discard(partial)
                    raise httpx.TransportError("El servidor contestó otro rango.")
            else:
                raise UpdateError(f"El servidor respondió {status}.")
            received = offset
            with _open_partial(partial, append=offset > 0) as handle:
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > manifest.size:
                        raise InstallerIntegrityError(
                            "La descarga supera el tamaño del manifiesto."
                        )
                    handle.write(chunk)
                    on_progress(received)


def _usable_size(partial: Path, full_size: int) -> int:
    """Bytes ya bajados; un parcial más grande que el instalador se descarta."""
    try:
        size = partial.stat().st_size
    except OSError:
        return 0
    if size > full_size:
        partial.unlink(missing_ok=True)
        return 0
    return size


def _discard(path: Path) -> None:
    path.unlink(missing_ok=True)


def _open_partial(partial: Path, *, append: bool) -> BinaryIO:
    return partial.open("ab" if append else "wb")


def _download_identity(manifest: ReleaseManifest) -> str:
    return json.dumps({"url": manifest.url, "sha256": manifest.sha256, "size": manifest.size})


def _same_download(meta: Path, manifest: ReleaseManifest) -> bool:
    try:
        return meta.read_text(encoding="utf-8") == _download_identity(manifest)
    except OSError:
        return False


def _client(
    timeout: httpx.Timeout, transport: httpx.AsyncBaseTransport | None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
        transport=transport,
    )


async def _get_small(client: httpx.AsyncClient, url: str) -> bytes:
    try:
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise UpdateError(f"{url} respondió {response.status_code}.")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MANIFEST_MAX_BYTES:
                    raise UpdateError(f"{url} es demasiado grande para ser un manifiesto.")
            return bytes(body)
    except httpx.HTTPError as exc:
        raise UpdateError(f"No se pudo leer {url}: {exc}") from exc
