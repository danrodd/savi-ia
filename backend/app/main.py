from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.infrastructure.config import get_settings
from app.infrastructure.database import close_engines, get_agent_engine, init_engines
from app.modules.chat.infrastructure.http import router as chat_router
from app.modules.conversations.infrastructure.http import router as conversations_router
from app.shared.exceptions import register_exception_handlers


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    init_engines(settings)
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

    app.include_router(conversations_router)
    app.include_router(chat_router)

    return app


app = create_app()
