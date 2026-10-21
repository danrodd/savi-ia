"""Lectura del servidor de actualizaciones por HTTPS.

Sin redirecciones: el servidor sirve archivos estáticos y no tiene motivo para
redirigir. Toda falla de red se traduce a `UpdateError`, así el coordinador
la registra y SAVI sigue funcionando.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.modules.updates.domain.exceptions import InstallerIntegrityError, UpdateError
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


class HttpManifestSource(ManifestSource):
    def __init__(
        self,
        *,
        base_url: str,
        channel: str,
        public_key: Ed25519PublicKey,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._manifest_url = f"{base_url.rstrip('/')}/{channel}.json"
        self._public_key = public_key
        # Solo para tests: simular el servidor sin red.
        self._transport = transport

    async def fetch(self) -> ReleaseManifest:
        async with _client(_MANIFEST_TIMEOUT, self._transport) as client:
            manifest_bytes = await _get_small(client, self._manifest_url)
            signature = await _get_small(client, f"{self._manifest_url}.sig")
        return verify_manifest(self._public_key, manifest_bytes, signature)


class HttpInstallerDownloader(InstallerDownloader):
    def __init__(
        self, *, target_dir: Path, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._target_dir = target_dir
        self._transport = transport

    async def download(self, manifest: ReleaseManifest, on_progress: Callable[[int], None]) -> Path:
        self._target_dir.mkdir(parents=True, exist_ok=True)
        # Una descarga vieja no sirve para nada: se borra antes de bajar otra.
        for old in self._target_dir.glob("SAVI-Setup-*"):
            old.unlink(missing_ok=True)

        name = manifest.url.rsplit("/", 1)[-1]
        target = self._target_dir / name
        partial = target.with_name(f"{name}.partial")
        try:
            async with (
                _client(_DOWNLOAD_TIMEOUT, self._transport) as client,
                client.stream("GET", manifest.url) as response,
            ):
                if response.status_code != 200:
                    raise UpdateError(f"El servidor respondió {response.status_code}.")
                received = 0
                with partial.open("wb") as handle:
                    async for chunk in response.aiter_bytes():
                        received += len(chunk)
                        if received > manifest.size:
                            raise InstallerIntegrityError(
                                "La descarga supera el tamaño del manifiesto."
                            )
                        handle.write(chunk)
                        on_progress(received)
            # Hashear 160 MB bloquearía el event loop.
            await asyncio.to_thread(verify_installer, partial, manifest)
        except httpx.HTTPError as exc:
            partial.unlink(missing_ok=True)
            raise UpdateError("No se pudo descargar la actualización.") from exc
        except UpdateError:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(target)
        return target


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
