"""Techo general por IP.

Cubre lo que no tiene dependency propia, incluido `/health`, que es público y
antes hacía un `SELECT 1`: una ráfaga sin credenciales degradaba toda la app.

Es un techo alto (300/min por default), no el límite fino. Los límites que
importan (login, chat, subida) están en `guards.py` con su propia clave.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.infrastructure.config import get_settings
from app.shared.rate_limit.guards import client_ip, get_rate_limiter
from app.shared.rate_limit.sliding_window import RateLimitPolicy, SlidingWindowRateLimiter

# Cada cuánto se limpian claves viejas. Sin esto el diccionario crece con cada
# IP nueva y un atacante rotando origen se lleva la memoria del proceso.
_PURGE_EVERY_SECONDS = 300.0
_PURGE_OLDER_THAN_SECONDS = 3600.0


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        super().__init__(app)  # pyright: ignore[reportArgumentType]
        self._last_purge = time.monotonic()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return await call_next(request)

        limiter = get_rate_limiter()
        self._maybe_purge(limiter)

        key = f"global:{client_ip(request, settings)}"
        decision = limiter.check(key, RateLimitPolicy(settings.rate_limit_global_per_minute, 60.0))
        if not decision.allowed:
            # Respuesta armada acá y no por excepción: el middleware corre
            # fuera del alcance de los `exception_handler` de FastAPI.
            return JSONResponse(
                status_code=429,
                content={
                    "errorCode": "rate_limited",
                    "detail": "Demasiados pedidos. Esperá unos segundos.",
                },
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )
        return await call_next(request)

    def _maybe_purge(self, limiter: SlidingWindowRateLimiter) -> None:
        now = time.monotonic()
        if now - self._last_purge < _PURGE_EVERY_SECONDS:
            return
        self._last_purge = now
        limiter.purge(_PURGE_OLDER_THAN_SECONDS)
