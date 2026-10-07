"""Crea la base de Postgres de SAVI si todavía no existe.

Instalar SAVI tiene que alcanzar con el instalador: las tablas ya las crea
`ensure_schema`, pero la base en sí había que crearla antes a mano, y sin
ella el diagnóstico solo decía "connection was closed in the middle of
operation" (con el servidor en español, asyncpg no puede leer el mensaje
"no existe la base de datos" y corta la conexión). Ese mensaje no le dice
a nadie qué hacer.

Se consulta `pg_database` desde la base de mantenimiento en vez de
intentar conectarse y esperar el error, justamente por eso.
"""

from __future__ import annotations

from sqlalchemy import URL, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.infrastructure.config.settings import Settings

# Bases que existen en todo servidor Postgres y sirven para conectarse
# cuando la de SAVI todavía no existe. `template1` cubre los servidores
# donde borraron `postgres`.
_MAINTENANCE_DATABASES = ("postgres", "template1")
_CONNECT_TIMEOUT_SECONDS = 10
# SQLSTATE de "permiso denegado" (insufficient_privilege).
_INSUFFICIENT_PRIVILEGE = "42501"


class AgentDatabaseCreationError(Exception):
    """La base no existe y no se pudo crear. El mensaje es para el técnico."""


async def ensure_agent_database(settings: Settings) -> bool:
    """Devuelve True si la creó, False si ya existía (o no es Postgres)."""
    if settings.agent_db_engine != "postgresql":
        return False
    name = settings.agent_db_name or ""
    last_error: Exception | None = None
    for maintenance in _MAINTENANCE_DATABASES:
        # AUTOCOMMIT: `CREATE DATABASE` no puede correr dentro de una transacción.
        engine = create_async_engine(
            _maintenance_url(settings, maintenance),
            isolation_level="AUTOCOMMIT",
            connect_args={"timeout": _CONNECT_TIMEOUT_SECONDS},
        )
        try:
            async with engine.connect() as connection:
                return await _create_if_missing(connection, name, settings.agent_db_user or "")
        except AgentDatabaseCreationError:
            raise
        except Exception as error:  # noqa: BLE001 - se prueba la siguiente base
            last_error = error
        finally:
            await engine.dispose()
    assert last_error is not None
    raise last_error


async def _create_if_missing(connection: AsyncConnection, name: str, user: str) -> bool:
    exists = await connection.scalar(
        text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
    )
    if exists:
        return False
    quoted = '"' + name.replace('"', '""') + '"'
    try:
        await connection.execute(text(f"CREATE DATABASE {quoted}"))
    except DBAPIError as error:
        if getattr(error.orig, "pgcode", None) != _INSUFFICIENT_PRIVILEGE:
            raise
        raise AgentDatabaseCreationError(
            f"La base '{name}' no existe y el usuario '{user}' no tiene permiso "
            f"para crearla. Pedile al administrador del servidor que la cree "
            f"(CREATE DATABASE {quoted};) o usá un usuario con permiso CREATEDB."
        ) from None
    return True


def _maintenance_url(settings: Settings, database: str) -> URL:
    # `URL.create` escapa la contraseña: una con '@' o ':' rompía la URL armada a mano.
    return URL.create(
        "postgresql+asyncpg",
        username=settings.agent_db_user,
        password=settings.agent_db_password,
        host=settings.agent_db_host,
        port=settings.agent_db_port,
        database=database,
    )
