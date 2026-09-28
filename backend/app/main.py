import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text

from app._version import __built_at__, __commit__, __version__
from app.infrastructure.config import get_settings
from app.infrastructure.database import (
    close_engines,
    get_agent_engine,
    get_agent_sessionmaker,
    init_engines,
)
from app.modules.auth.infrastructure.http import router as auth_router
from app.modules.auth.infrastructure.http.admin import SaviAdminDep
from app.modules.chat.infrastructure.http import router as chat_router
from app.modules.company_knowledge.infrastructure.http import (
    public_router as company_documents_public_router,
)
from app.modules.company_knowledge.infrastructure.http import (
    router as company_documents_router,
)
from app.modules.company_knowledge.infrastructure.http import (
    web_router as company_web_sources_router,
)
from app.modules.company_knowledge.infrastructure.provider import (
    start_company_knowledge,
    stop_company_knowledge,
)
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
from app.modules.knowledge.infrastructure.catalog_provider import init_catalog
from app.modules.llm_providers.infrastructure.active_provider_resolver import (
    init_active_provider_resolver,
)
from app.modules.llm_providers.infrastructure.http import router as llm_providers_router
from app.modules.llm_providers.infrastructure.http.dependencies import (
    build_llm_provider_repository,
)
from app.modules.llm_providers.infrastructure.seed import seed_llm_providers
from app.modules.usage.infrastructure.http import router as usage_router
from app.paths import resource_dir
from app.shared.exceptions import register_exception_handlers
from app.shared.middleware import SecurityHeadersMiddleware
from app.shared.rate_limit import GlobalRateLimitMiddleware
from app.shared.security import FernetCredentialCipher

# Prefijos que pertenecen al API. Una ruta desconocida bajo alguno de
# ellos es un 404 del API, no la SPA: devolver HTML ahí convierte un
# typo en una hora de debugging.
_API_PREFIXES = (
    "auth",
    "chat",
    "conversations",
    "usage",
    # Bajo `/admin` conviven el API y las pantallas del frontend, así que se
    # listan los prefijos COMPLETOS del API. Poner solo "admin" hacía que
    # `/admin/consumo` y las demás pantallas devolvieran un 404 JSON.
    "admin/company-documents",
    "admin/company-web-sources",
    "admin/erp-databases",
    "admin/llm-providers",
    "erp-databases",
    "company-documents",
    "health",
    "version",
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
    if settings.uses_insecure_jwt_secret:
        # Fuera de desarrollo esto ni siquiera arranca (lo valida Settings).
        # Acá el aviso es para que no se filtre a un despliegue por descuido.
        logger.warning(
            "JWT_SECRET tiene el valor de fábrica: cualquiera que lo conozca puede "
            "firmarse un token de administrador. Generá uno antes de salir de desarrollo."
        )
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

    # Proveedor de IA: la primera vez se siembra Claude desde el `.env`; a
    # partir de ahí se administra desde la aplicación y el chat lo resuelve
    # por turno.
    llm_repository = build_llm_provider_repository(settings)
    await seed_llm_providers(llm_repository, settings)
    init_active_provider_resolver(llm_repository)

    # Carga del catálogo de conocimiento al startup. Si los archivos
    # están corruptos o faltan datos requeridos, falla loud — preferimos
    # crashear que servir respuestas sin knowledge.
    # Vía `resource_dir()` y no `__file__`: empaquetado, `__file__` apunta a
    # una ruta sintética dentro del bundle y la resolución deja de ser obvia.
    knowledge_root = resource_dir() / "app" / "modules" / "knowledge" / "data"
    init_catalog(knowledge_root)

    # Documentos de la empresa: worker de ingesta + índice en memoria. La
    # carga del índice corre en segundo plano y no demora el arranque.
    await start_company_knowledge(settings)
    try:
        yield
    finally:
        await stop_company_knowledge()
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

    # Cabeceras de seguridad en toda respuesta, incluida la SPA.
    app.add_middleware(SecurityHeadersMiddleware)

    # Techo por IP para todo, incluido lo público. Se registra ANTES que CORS
    # para que quede por fuera: un pedido rechazado no debería gastar nada más.
    app.add_middleware(GlobalRateLimitMiddleware)

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
        """Vivo o no. **No toca la base de datos a propósito**: es el endpoint
        público más golpeado, así que cualquier trabajo real acá amplifica un
        DoS aun con el techo por IP del middleware. Medido antes del cambio:
        200 pedidos concurrentes llevaban la mediana a ~1 s porque cada uno
        hacía un `SELECT 1`. Para chequear la BD está `/health/db`, que pide
        administrador."""
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
            "version": __version__,
        }

    @app.get("/health/db", tags=["system"])
    async def health_db(_admin: SaviAdminDep) -> dict[str, str | float]:
        started = time.perf_counter()
        async with get_agent_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "latencia_ms": round((time.perf_counter() - started) * 1000, 1)}

    @app.get("/version", tags=["system"])
    async def version() -> dict[str, str | None]:
        """Qué build está corriendo. Sin autenticación, como `/health`:
        es lo primero que pregunta soporte y no expone nada sensible."""
        return {
            "version": __version__,
            "commit": __commit__,
            "compilado": __built_at__,
            "entorno": settings.app_env,
        }

    app.include_router(auth_router)
    app.include_router(conversations_router)
    app.include_router(chat_router)
    app.include_router(usage_router)
    app.include_router(erp_databases_router)
    app.include_router(erp_databases_public_router)
    app.include_router(llm_providers_router)
    app.include_router(company_documents_router)
    app.include_router(company_documents_public_router)
    app.include_router(company_web_sources_router)

    # Va último: la ruta catch-all tiene que perder contra cualquier ruta
    # del API, y FastAPI resuelve por orden de registro.
    _mount_frontend(app)

    return app


def _belongs_to_the_api(path: str) -> bool:
    """¿Esta ruta desconocida es del API o de `vue-router`?

    Se compara contra prefijos COMPLETOS, no contra el primer segmento. El
    frontend tiene sus propias rutas bajo `/admin` (`/admin/consumo`,
    `/admin/conocimiento`, `/admin/bases`) y el API también (`/admin/
    company-documents`, …). Mirando solo el primer segmento, **todas las
    pantallas de administración devolvían un 404 JSON** al recargarlas o al
    entrar por enlace directo en la app instalada. En desarrollo no se veía
    porque ahí la SPA la sirve Vite.
    """
    normalizada = path.strip("/")
    return any(
        normalizada == prefijo or normalizada.startswith(f"{prefijo}/")
        for prefijo in _API_PREFIXES
    )


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
        if _belongs_to_the_api(spa_path):
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
