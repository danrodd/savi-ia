from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.infrastructure.config.settings import Settings

_agent_engine: AsyncEngine | None = None

# El engine del ERP ya NO vive acá. Con varias bases de clientes
# registradas no hay "el" ERP: cada turno resuelve la suya. Ver
# `app/modules/erp_databases/infrastructure/engine_registry.py`.


def _build_sqlite_agent_engine(settings: Settings) -> AsyncEngine:
    """Engine SQLite para instalación de escritorio.

    Dos PRAGMA no son opcionales acá:

    - `foreign_keys=ON`: SQLite las ignora por default. Sin esto los
      `ondelete="CASCADE"` de `messages` y el `SET NULL` de
      `superseded_by_id` no se aplican y quedan filas huérfanas.
    - `journal_mode=WAL`: el módulo `chat` escribe desde tareas con
      sessionmaker propio que sobreviven a la cancelación del cliente.
      Con el journal por default esos writes compiten con las lecturas
      del request y salta "database is locked".
    """
    engine = create_async_engine(
        settings.agent_db_url,
        echo=settings.app_debug,
        # `timeout` es del driver: cuánto espera por el lock antes de
        # abortar. No confundir con los pool_size de Postgres, que
        # SQLite no acepta.
        connect_args={"timeout": 30.0},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _apply_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            # NORMAL + WAL es durable ante crash de proceso (no ante corte
            # de energía) y evita un fsync por commit. Para un chat local
            # es el punto correcto entre seguridad y latencia.
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()
    # NO poner acá un `BEGIN IMMEDIATE` global (se probó y se revirtió).
    #
    # Suena a la solución de manual para el "database is locked" de
    # SQLite, y en un servicio con transacciones cortas lo es. Acá no: un
    # turno del chat mantiene una transacción abierta mientras el LLM
    # responde, y adentro de ese turno la tool de consulta libre pide una
    # conexión nueva para auditar. Con el BEGIN diferido esa transacción
    # larga solo sostiene un snapshot de lectura y la escritura interna
    # pasa; con IMMEDIATE pasa a retener el lock EXCLUSIVO durante todo
    # el turno y la escritura interna se cuelga hasta agotar el timeout.
    # Es un abrazo mortal consigo mismo: se convirtió una carrera
    # ocasional en un fallo garantizado de 30 s por turno.
    #
    # La causa de fondo es la transacción que vive lo que dura el turno.
    # Mientras siga así, no hay PRAGMA que la tape.

    return engine


def _build_postgres_agent_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.agent_db_url,
        echo=settings.app_debug,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=5,
    )


def init_engines(settings: Settings) -> None:
    global _agent_engine

    if settings.agent_db_engine == "sqlite":
        _agent_engine = _build_sqlite_agent_engine(settings)
    else:
        _agent_engine = _build_postgres_agent_engine(settings)


def get_agent_engine() -> AsyncEngine:
    if _agent_engine is None:
        raise RuntimeError("Agent engine not initialized. Call init_engines() at startup.")
    return _agent_engine


async def close_engines() -> None:
    global _agent_engine
    if _agent_engine is not None:
        await _agent_engine.dispose()
        _agent_engine = None
