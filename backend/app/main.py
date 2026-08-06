from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text

from app.infrastructure.config import get_settings
from app.infrastructure.database import close_engines, get_agent_engine, init_engines
from app.modules.auth.infrastructure.http import router as auth_router
from app.modules.chat.infrastructure.http import router as chat_router
from app.modules.conversations.infrastructure.http import router as conversations_router
from app.modules.knowledge.infrastructure.catalog_provider import init_catalog
from app.modules.usage.infrastructure.http import router as usage_router
from app.paths import resource_dir
from app.shared.exceptions import register_exception_handlers

# Prefijos que pertenecen al API. Una ruta desconocida bajo alguno de
# ellos es un 404 del API, no la SPA: devolver HTML ahí convierte un
# typo en una hora de debugging.
_API_PREFIXES = (
    "auth",
    "chat",
    "conversations",
    "usage",
    "health",
    "docs",
    "redoc",
    "openapi.json",
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    init_engines(settings)
    # Carga del catálogo de conocimiento al startup. Si los archivos
    # están corruptos o faltan datos requeridos, falla loud — preferimos
    # crashear que servir respuestas sin knowledge.
    # Vía `resource_dir()` y no `__file__`: empaquetado, `__file__` apunta a
    # una ruta sintética dentro del bundle y la resolución deja de ser obvia.
    knowledge_root = resource_dir() / "app" / "modules" / "knowledge" / "data"
    init_catalog(knowledge_root)
    try:
        yield
    finally:
        await close_engines()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    if settings.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        async with get_agent_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

    app.include_router(auth_router)
    app.include_router(conversations_router)
    app.include_router(chat_router)
    app.include_router(usage_router)

    # Va último: la ruta catch-all tiene que perder contra cualquier ruta
    # del API, y FastAPI resuelve por orden de registro.
    _mount_frontend(app)

    return app


def _mount_frontend(app: FastAPI) -> None:
    """Sirve el build de Vue desde el mismo origen que el API.

    Solo aplica a la instalación de escritorio, donde el .exe es el único
    proceso. En desarrollo el frontend lo sirve Vite y esta función no
    hace nada porque no existe el directorio del build.
    """
    dist = resource_dir() / "frontend"
    index = dist / "index.html"
    if not index.is_file():
        return

    @app.get("/{spa_path:path}", include_in_schema=False)
    async def serve_spa(spa_path: str) -> FileResponse:
        first_segment = spa_path.split("/", 1)[0]
        if first_segment in _API_PREFIXES:
            raise HTTPException(status_code=404, detail="Not Found")

        # `spa_path` viene del cliente: sin este chequeo un
        # `../../.env` serviría archivos fuera del build.
        candidate = (dist / spa_path).resolve()
        if spa_path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)

        # Cualquier otra ruta la resuelve vue-router en el cliente
        # (`createWebHistory` necesita este fallback).
        return FileResponse(index)


app = create_app()
