"""Guarda contra SSRF para la importación desde la web.

SAVI corre en el servidor del cliente, dentro de su red. Una URL maliciosa
o mal escrita (`http://localhost:5433`, `http://192.168.1.10/admin`,
`http://169.254.169.254/`) haría que el servidor pidiera recursos
internos. Reglas, en cada conexión y en cada redirección:

- solo `http` y `https`, en los puertos 80 y 443;
- el DNS se resuelve UNA vez y todas las IPs deben ser públicas;
- se conecta a esa IP (ver `safe_http.py`), así una segunda resolución no
  puede cambiarla (DNS rebinding).
"""

import asyncio
import ipaddress
import socket
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.modules.company_knowledge.domain.exceptions import UnsafeUrlError

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_PORTS = frozenset({80, 443})
IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


@dataclass(frozen=True, slots=True)
class SafeTarget:
    scheme: str
    host: str
    port: int
    ip: IpAddress


def _is_public(ip: IpAddress) -> bool:
    # IPv4 mapeada en IPv6 (`::ffff:127.0.0.1`): se evalúa la IPv4.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    # `is_global` ya excluye privadas, loopback, link-local (metadatos de
    # nube), CGNAT, reservadas y de documentación. Multicast se agrega
    # aparte porque algunos rangos multicast figuran como globales.
    return ip.is_global and not ip.is_multicast


def split_url(url: str) -> tuple[str, str, int]:
    """Esquema, host y puerto, o `UnsafeUrlError` si la URL no es válida."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise UnsafeUrlError("La dirección no es una URL válida.") from exc
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("Solo se pueden leer direcciones http:// o https://.")
    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise UnsafeUrlError("La dirección no tiene un sitio válido.")
    if parts.username or parts.password:
        raise UnsafeUrlError("La dirección no puede incluir usuario ni contraseña.")
    effective_port = port or (443 if scheme == "https" else 80)
    if effective_port not in ALLOWED_PORTS:
        raise UnsafeUrlError("Solo se pueden leer sitios en los puertos 80 y 443.")
    return scheme, host, effective_port


async def resolve_safe_target(url: str, allowed_private_hosts: Sequence[str] = ()) -> SafeTarget:
    """Valida la URL y devuelve la IP pública a la que hay que conectar."""
    scheme, host, port = split_url(url)
    allow_private = host in {h.strip().lower() for h in allowed_private_hosts}
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        ips: list[IpAddress] = [literal]
    else:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
        except socket.gaierror as exc:
            raise UnsafeUrlError(f"No se encontró el sitio {host}.") from exc
        ips = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not ips:
        raise UnsafeUrlError(f"No se encontró el sitio {host}.")
    # TODAS deben ser públicas: si una sola es interna, un atacante podría
    # lograr que la conexión use esa.
    if not allow_private and not all(_is_public(ip) for ip in ips):
        raise UnsafeUrlError(
            "La dirección apunta a la red interna o a este servidor; por seguridad no se lee."
        )
    return SafeTarget(scheme=scheme, host=host, port=port, ip=ips[0])
