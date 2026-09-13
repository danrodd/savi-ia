import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.infrastructure.config import get_settings
from app.infrastructure.database.base import Base
from app.modules.auth.infrastructure.persistence.models import RefreshTokenModel  # noqa: F401
from app.modules.conversations.infrastructure.persistence.models import (  # noqa: F401
    ConversationModel,
    MessageModel,
)
from app.modules.erp_databases.infrastructure.persistence.models import (  # noqa: F401
    ErpDatabaseModel,
)
from app.modules.free_query.infrastructure.models import AuditQueryModel  # noqa: F401

config = context.config

# `configure_logger` es la convención de Alembic para uso embebido, y acá
# no es cosmética: `fileConfig()` REEMPLAZA los handlers del root logger
# por los de alembic.ini (un StreamHandler a stderr, level WARN) y
# desactiva los loggers ya creados.
#
# Cuando alembic corre solo, eso es lo correcto: es dueño del proceso.
# Pero el launcher de escritorio llama a `ensure_schema()` al arrancar, y
# ahí el efecto es que el archivo de log del cliente queda mudo desde la
# migración en adelante — justo antes de que la aplicación empiece a
# atender peticiones, así que ningún error 500 se llegaba a registrar y
# soporte se quedaba sin nada que leer.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.agent_db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite no soporta la mayoría de los `ALTER TABLE`. El modo batch
        # los emula recreando la tabla; en Postgres no cambia nada.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
