from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings, get_settings
from app.db import create_engine
from app.logging_config import configure_logging
from app.modules.health.presentation import router as health_router

logger = logging.getLogger("savi_cloud.access")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cache-Control": "no-store",
}


def create_app(settings: Settings | None = None, engine: AsyncEngine | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    owns_engine = engine is None
    engine = engine or create_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        if owns_engine:
            await engine.dispose()

    dev = settings.env == "development"
    app = FastAPI(
        title="SAVI Cloud",
        lifespan=lifespan,
        docs_url="/docs" if dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if dev else None,
    )
    app.state.engine = engine
    app.state.settings = settings

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            # Solo método, ruta y estado: sin query string, cabeceras ni cuerpo.
            logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(health_router)
    return app
