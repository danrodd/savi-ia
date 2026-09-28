"""Descarga simple con la guarda contra SSRF en cada salto.

- Resuelve y valida el destino (`url_safety.resolve_safe_target`) y conecta
  a esa IP con el `Host` y el SNI del sitio: el certificado se valida contra
  el nombre del sitio y una segunda resolución DNS no puede redirigir la
  conexión a la red interna.
- Sigue las redirecciones a mano (máximo 5), validando cada una.
- Corta la descarga al superar el tope de tamaño.
- Un cliente por pedido y sin keep-alive: una conexión TLS abierta para un
  sitio nunca se reutiliza para otro que comparta la IP.
"""

import time
import urllib.robotparser
from collections.abc import Awaitable, Callable, Sequence
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.modules.company_knowledge.domain.entities.web_source import FetchResult
from app.modules.company_knowledge.domain.exceptions import UnsafeUrlError, WebFetchError
from app.modules.company_knowledge.domain.interfaces import WebFetcher
from app.modules.company_knowledge.infrastructure.web.url_safety import (
    SafeTarget,
    resolve_safe_target,
)

Resolver = Callable[[str, Sequence[str]], Awaitable[SafeTarget]]
USER_AGENT = "SAVI-Knowledge/1.0 (+lectura de conocimiento de la empresa)"
MAX_REDIRECTS = 5
_ROBOTS_TTL_S = 3600.0


def _pinned_url(url: str, target: SafeTarget) -> str:
    parts = urlsplit(url)
    ip = f"[{target.ip}]" if target.ip.version == 6 else str(target.ip)
    netloc = ip if target.port in (80, 443) else f"{ip}:{target.port}"
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))


class SafeHttpFetcher(WebFetcher):
    def __init__(
        self,
        *,
        timeout_s: float,
        max_bytes: int,
        allowed_private_hosts: Sequence[str] = (),
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = resolve_safe_target,
    ) -> None:
        self._timeout_s = timeout_s
        self._max_bytes = max_bytes
        self._allowed_private_hosts = tuple(allowed_private_hosts)
        # Solo para tests: simular el servidor y el DNS sin red. En
        # producción el resolutor es siempre `resolve_safe_target`.
        self._transport = transport
        self._resolve = resolver
        self._robots: dict[str, tuple[float, urllib.robotparser.RobotFileParser]] = {}

    async def fetch(
        self, url: str, *, etag: str | None = None, last_modified: str | None = None
    ) -> FetchResult:
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            target = await self._resolve(current, self._allowed_private_hosts)
            response = await self._request(current, target, headers)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise WebFetchError("El sitio respondió una redirección sin destino.")
                current = urljoin(current, location)
                continue
            return response_to_result(current, response)
        raise WebFetchError("El sitio redirige demasiadas veces.")

    async def validate(self, url: str) -> None:
        await self._resolve(url, self._allowed_private_hosts)

    async def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        cached = self._robots.get(origin)
        if cached is None or time.monotonic() - cached[0] > _ROBOTS_TTL_S:
            parser = urllib.robotparser.RobotFileParser()
            try:
                result = await self.fetch(f"{origin}/robots.txt")
                if result.status_code == 200:
                    parser.parse(result.text.splitlines())
                else:
                    # Sin robots.txt (404) todo está permitido.
                    parser.parse([])
            except (WebFetchError, UnsafeUrlError):
                parser.parse([])
            cached = (time.monotonic(), parser)
            self._robots[origin] = cached
        return cached[1].can_fetch(USER_AGENT, url)

    async def _request(
        self, url: str, target: SafeTarget, headers: dict[str, str]
    ) -> httpx.Response:
        host_header = target.host if target.port in (80, 443) else f"{target.host}:{target.port}"
        request_headers = {**headers, "Host": host_header}
        limits = httpx.Limits(max_keepalive_connections=0)
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s,
                follow_redirects=False,
                limits=limits,
                transport=self._transport,
            ) as client:
                request = client.build_request(
                    "GET",
                    _pinned_url(url, target),
                    headers=request_headers,
                    extensions={"sni_hostname": target.host},
                )
                streamed = await client.send(request, stream=True)
                try:
                    body = bytearray()
                    async for chunk in streamed.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            limit_mb = self._max_bytes // (1024 * 1024)
                            raise WebFetchError(f"La página supera el tope de {limit_mb} MB.")
                finally:
                    await streamed.aclose()
                # Respuesta ya leída y acotada: `text` decodifica con el
                # charset declarado, como un pedido normal. `aiter_bytes` ya
                # descomprimió el gzip: sin quitar `content-encoding`, httpx
                # intentaría descomprimir otra vez y fallaría con casi todos
                # los sitios reales.
                decoded_headers = [
                    (name, value)
                    for name, value in streamed.headers.multi_items()
                    if name.lower() not in ("content-encoding", "content-length")
                ]
                return httpx.Response(
                    streamed.status_code, headers=decoded_headers, content=bytes(body)
                )
        except httpx.TimeoutException as exc:
            raise WebFetchError("El sitio tardó demasiado en responder.") from exc
        except httpx.DecodingError as exc:
            raise WebFetchError(f"No se pudo leer la respuesta de {target.host}.") from exc
        except httpx.HTTPError as exc:
            raise WebFetchError(f"No se pudo conectar con {target.host}.") from exc


def response_to_result(url: str, response: httpx.Response) -> FetchResult:
    content_type = response.headers.get("content-type", "").lower()
    body = response.content
    text = ""
    if "html" in content_type or "text" in content_type or "xml" in content_type:
        text = response.text
    return FetchResult(
        url=url,
        status_code=response.status_code,
        content_type=content_type,
        body=body,
        text=text,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
    )
