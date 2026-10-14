from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings, get_settings
from app.db import create_engine, create_sessionmaker
from app.dependencies import RateLimiters
from app.logging_config import configure_logging
from app.modules.alerts.presentation import router as alerts_router
from app.modules.alerts.runner import start_alert_task, stop_alert_task
from app.modules.console.presentation import router as console_api_router
from app.modules.enrollments.presentation import router as enrollments_router
from app.modules.health.presentation import router as health_router
from app.modules.ingest.presentation import router as ingest_router
from app.modules.instances.presentation import router as instances_router
from app.modules.metrics.presentation import router as metrics_router
from app.modules.staff.presentation import auth_router as console_auth_router
from app.modules.staff.presentation import console_router
from app.modules.staff.security import StaffSecurity
from app.shared.clock import Clock, utc_now
from app.shared.http_errors import install_error_handlers
from app.spa import mount_console

logger = logging.getLogger("savi_cloud.access")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cache-Control": "no-store",
}


def create_app(
    settings: Settings | None = None,
    engine: AsyncEngine | None = None,
    clock: Clock = utc_now,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    owns_engine = engine is None
    engine = engine or create_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        alert_task = start_alert_task(app.state.sessionmaker, settings, clock)
        try:
            yield
        finally:
            await stop_alert_task(alert_task)
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
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.clock = clock
    # Límites de tasa en memoria (una réplica). Se reinician con el proceso.
    app.state.limiters = RateLimiters.create(clock)
    app.state.staff_security = (
        StaffSecurity(settings.console_secret, clock) if settings.console_secret else None
    )
    install_error_handlers(app)

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
    app.include_router(enrollments_router)
    app.include_router(instances_router)
    app.include_router(ingest_router)
    app.include_router(console_auth_router)
    app.include_router(console_router)
    app.include_router(console_api_router)
    app.include_router(metrics_router)
    app.include_router(alerts_router)
    # Siempre al final: es un comodín y las rutas del API deben ganar.
    if settings.console_static_dir:
        mount_console(app, Path(settings.console_static_dir))
    return app
