"""Cabeceras de seguridad del navegador.

Defensa en profundidad: nada de esto arregla un bug, pero acota el daño si
aparece uno. SAVI sirve el frontend desde el mismo origen que el API, así que
una sola política alcanza.

La CSP es restrictiva y a la vez realista con lo que la app hace hoy:

- `'unsafe-inline'` en estilos porque Vue inyecta estilos de componente en
  runtime; quitarlo rompería la interfaz entera.
- `blob:` en `img-src` y `frame-src` porque abrir un documento citado y
  descargar un diagrama pasan por `URL.createObjectURL`.
- `connect-src 'self'` alcanza: el frontend solo habla con su propio backend,
  y es el backend el que sale hacia el proveedor de IA.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_CSP = "; ".join(
    (
        "default-src 'self'",
        # Sin `'unsafe-inline'`: el script que aplica el tema antes del primer
        # pintado vive en `/theme-init.js` justamente para no tener que
        # abrirlo. Medido contra la SPA compilada: embebido, la CSP lo
        # bloqueaba y volvía el destello claro al cargar.
        "script-src 'self'",
        # Google Fonts. Ideal sería alojarlas con la app —el escritorio tiene
        # que funcionar sin internet— pero eso es otro cambio; hoy sin esto
        # la tipografía se cae a la del sistema.
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "img-src 'self' data: blob:",
        "font-src 'self' data: https://fonts.gstatic.com",
        "connect-src 'self'",
        # Abrir el PDF de un documento citado usa un blob:.
        "frame-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        # Equivalente moderno de X-Frame-Options: DENY.
        "frame-ancestors 'none'",
    )
)

_HEADERS = {
    "Content-Security-Policy": _CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # SAVI no usa cámara, micrófono ni ubicación.
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in _HEADERS.items():
            # `setdefault`: la descarga de documentos ya fija su propio
            # `X-Content-Type-Options`, y no hay que pisar lo que una ruta
            # decidió a conciencia.
            response.headers.setdefault(name, value)
        return response
