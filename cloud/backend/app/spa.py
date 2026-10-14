"""Sirve la consola web (SPA ya compilada) desde el mismo origen que el API.

Mismo origen = sin CORS y con la cookie de refresh en `SameSite=Strict`. Las rutas del API
se registran antes, así que tienen prioridad; esta ruta solo atrapa lo que no es API.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse

from app.shared.http_errors import ApiError

# Prefijos que pertenecen al API: nunca deben caer en el `index.html` de la consola.
_API_PREFIXES = ("api/", "console/", "docs", "openapi.json")
_RESERVED = {"health", "ready"}

# La consola carga solo scripts y estilos propios y habla únicamente con su origen.
CONSOLE_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
_IMMUTABLE = "public, max-age=31536000, immutable"
_NO_CACHE = "no-cache"


def mount_console(app: FastAPI, directory: Path) -> None:
    root = directory.resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"La consola no está compilada: falta {index}")

    def _file(path: Path, cache: str) -> FileResponse:
        return FileResponse(
            path,
            headers={
                "Content-Security-Policy": CONSOLE_CSP,
                "Cache-Control": cache,
            },
        )

    @app.get("/{path:path}", include_in_schema=False)
    async def console_spa(path: str) -> Response:
        if path in _RESERVED or path.startswith(_API_PREFIXES):
            raise ApiError(404, "not_found", "No existe.")
        if path:
            candidate = (root / path).resolve()
            # `resolve()` colapsa `..`: un destino fuera de `root` no se sirve nunca.
            if root in candidate.parents and candidate.is_file():
                # Los assets llevan hash en el nombre: se pueden cachear sin límite.
                immutable = candidate.parent.name == "assets"
                return _file(candidate, _IMMUTABLE if immutable else _NO_CACHE)
        # Rutas de la SPA (/clientes/123): el router del navegador resuelve el resto.
        return _file(index, _NO_CACHE)
