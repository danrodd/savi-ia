from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.infrastructure.config.settings import Settings

_agent_engine: AsyncEngine | None = None
_erp_engine: AsyncEngine | None = None


def init_engines(settings: Settings) -> None:
    global _agent_engine, _erp_engine

    _agent_engine = create_async_engine(
        settings.agent_db_url,
        echo=settings.app_debug,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=5,
    )

    _erp_engine = create_async_engine(
        settings.erp_db_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=2,
        connect_args={
            "server_settings": {
                "default_transaction_read_only": "on",
                "statement_timeout": str(settings.erp_db_statement_timeout_ms),
            },
        },
    )


def get_agent_engine() -> AsyncEngine:
    if _agent_engine is None:
        raise RuntimeError("Agent engine not initialized. Call init_engines() at startup.")
    return _agent_engine


def get_erp_engine() -> AsyncEngine:
    if _erp_engine is None:
        raise RuntimeError("ERP engine not initialized. Call init_engines() at startup.")
    return _erp_engine


async def close_engines() -> None:
    global _agent_engine, _erp_engine
    if _agent_engine is not None:
        await _agent_engine.dispose()
        _agent_engine = None
    if _erp_engine is not None:
        await _erp_engine.dispose()
        _erp_engine = None
