import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text

from app._version import __version__
from app.infrastructure.config import get_settings
from app.infrastructure.database import (
    close_engines,
    get_agent_engine,
    get_agent_sessionmaker,
    init_engines,
)
from app.modules.auth.infrastructure.http import router as auth_router
from app.modules.chat.infrastructure.http import router as chat_router
from app.modules.conversations.infrastructure.http import router as conversations_router
from app.modules.erp_databases.infrastructure import (
    ErpConnectionProvider,
    backfill_legacy_rows,
    close_engine_registry,
    get_engine_registry,
    init_connection_provider,
    init_engine_registry,
    seed_default_database,
)
from app.modules.erp_databases.infrastructure.http import (
    public_router as erp_databases_public_router,
)
from app.modules.erp_databases.infrastructure.http import (
    router as erp_databases_router,
)
from app.modules.erp_databases.infrastructure.persistence import (
    SqlAlchemyErpDatabaseRepository,
)
from app.modules.erp_databases.infrastructure.security import FernetCredentialCipher
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
    "admin",
    "erp-databases",
    "health",
    "docs",
    "redoc",
    "openapi.json",
)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    # Primera línea del log de cada arranque: es lo primero que un
    # técnico de soporte busca para saber qué build tiene el cliente.
    logger.info("SAVI %s arrancando (env=%s)", __version__, settings.app_env)
    init_engines(settings)

    # Registry de engines del ERP: uno por base de cliente, creado en su
    # primer uso. Va antes del seed porque el repositorio de bases ya lo
    # necesita disponible.
    init_engine_registry(max_engines=settings.erp_max_open_engines)
    cipher = FernetCredentialCipher(
        settings.erp_credentials_key,
        old_keys=[settings.erp_credentials_key_old],
    )
    erp_repository = SqlAlchemyErpDatabaseRepository(get_agent_sessionmaker(), cipher)
    init_connection_provider(
        ErpConnectionProvider(erp_repository, get_engine_registry())
    )
    # Siembra la base default desde el `.env` la primera vez. Idempotente.
    await seed_default_database(erp_repository, settings)
    # Y recién ahí se pueden apuntar las filas anteriores al multi-BD:
    # antes de sembrar no hay base a la cual asignarlas.
    default_database = await erp_repository.get_default()
    if default_database is not None:
        await backfill_legacy_rows(
            get_agent_sessionmaker(), default_database.id
        )

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
        await close_engine_registry()
        await close_engines()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
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
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
            "version": __version__,
        }

    app.include_router(auth_router)
    app.include_router(conversations_router)
    app.include_router(chat_router)
    app.include_router(usage_router)
    app.include_router(erp_databases_router)
    app.include_router(erp_databases_public_router)

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
