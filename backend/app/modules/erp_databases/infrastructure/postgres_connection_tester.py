"""Impl `ConnectionTester` contra PostgreSQL.

No alcanza con `SELECT 1`: eso solo prueba que hay **un** Postgres del
otro lado. Verificamos además que el esquema sea el de un ERP de SEO.

Sin esa verificación se puede registrar cualquier base, y el error
aparecería recién a mitad de un chat, con un mensaje que un agente de
soporte no tiene cómo interpretar.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.domain.interfaces.connection_tester import (
    ConnectionTester,
    ConnectionTestResult,
)

logger = logging.getLogger(__name__)

# Timeout corto: probar una conexión es interactivo, alguien está
# esperando frente al formulario. El de runtime (60 s) sería eterno acá.
_TEST_TIMEOUT_MS = 5000
_CONNECT_TIMEOUT_S = 8.0

# Tablas que definen "esto es un ERP de SEO". Son justo las que consultan
# `auth` (usuarios, permisos, plan) y las tools MCP (empresa).
_REQUIRED_TABLES: tuple[tuple[str, str], ...] = (
    ("Seguridad", "Usuario"),
    ("Seguridad", "Formulario"),
    ("Seguridad", "PermisoFormulario"),
    ("SEO", "Modulo"),
    ("Empresa", "Empresa"),
)

_MISSING_TABLES_SQL = """
SELECT t.schema_name, t.table_name
FROM (VALUES {values}) AS t(schema_name, table_name)
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.tables it
    WHERE it.table_schema = t.schema_name AND it.table_name = t.table_name
)
"""

_RAZON_SOCIAL_SQL = 'SELECT "razonSocial" FROM "Empresa"."Empresa" ORDER BY "idEmpresa" LIMIT 1'


class PostgresConnectionTester(ConnectionTester):
    async def test(self, database: ErpDatabase) -> ConnectionTestResult:
        engine = _build_probe_engine(database)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

                missing = await _missing_tables(conn)
                if missing:
                    return ConnectionTestResult(
                        ok=False,
                        detail=(
                            "La conexión funciona, pero la base no parece ser un "
                            "ERP de SEO: faltan las tablas "
                            f"{', '.join(missing)}. Revisá que el nombre de la "
                            "base sea el correcto."
                        ),
                        missing_tables=missing,
                    )

                razon_social = await conn.scalar(text(_RAZON_SOCIAL_SQL))
                # `current_setting` y no `pg_roles`: no requiere permisos
                # especiales, así que también funciona con el rol acotado que
                # recomendamos.
                es_superusuario = (
                    str(await conn.scalar(text("SELECT current_setting('is_superuser')"))) == "on"
                )
        except Exception as e:  # noqa: BLE001
            # `Exception` y no `SQLAlchemyError` a propósito: probando
            # contra el ERP real, un host inalcanzable levanta
            # `asyncpg.ConnectionDoesNotExistError` y un timeout levanta
            # `TimeoutError`/`OSError` — ninguno hereda de SQLAlchemyError,
            # así que se escapaban y rompían el endpoint.
            #
            # El contrato de `ConnectionTester` es explícito: un dato de
            # conexión equivocado es entrada mal cargada, no una excepción
            # del sistema. Este método NUNCA levanta.
            logger.warning(
                "Prueba de conexión fallida contra %s:%s/%s: %s",
                database.host,
                database.port,
                database.database,
                type(e).__name__,
            )
            # Sin stacktrace ni credenciales en el mensaje al usuario. El
            # detalle técnico queda en el log.
            detail = _explain(e) or await _disambiguate(database)
            return ConnectionTestResult(ok=False, detail=detail)
        finally:
            await engine.dispose()

        name = str(razon_social) if razon_social else None
        base = f"Conexión correcta con {name}." if name else "Conexión correcta."
        if es_superusuario:
            # Avisar, no bloquear: hay instalaciones así y romperlas sería
            # peor que el riesgo. Con superusuario, cualquier falla del
            # validador de SQL escala a leer archivos del servidor.
            base += (
                " Atención: el usuario es SUPERUSUARIO de Postgres. Conviene un rol "
                "de solo lectura; ver la guía de alta de clientes."
            )
        return ConnectionTestResult(
            ok=True,
            detail=base,
            razon_social=name,
            is_superuser=es_superusuario,
        )


def _build_probe_engine(database: ErpDatabase) -> AsyncEngine:
    return create_async_engine(
        database.url,
        # Sin pool: es una conexión de una sola vez y se descarta.
        poolclass=None,
        echo=False,
        connect_args={
            "timeout": _CONNECT_TIMEOUT_S,
            "server_settings": {
                # Read-only también acá: probar una conexión nunca debe
                # poder escribir en la base de un cliente.
                "default_transaction_read_only": "on",
                "statement_timeout": str(_TEST_TIMEOUT_MS),
            },
        },
    )


async def _missing_tables(conn: AsyncConnection) -> tuple[str, ...]:
    """Devuelve cuáles de las tablas requeridas NO existen.

    Los nombres se interpolan en el SQL, pero vienen de `_REQUIRED_TABLES`
    —una constante del módulo—, nunca de entrada del usuario. Los datos
    que sí vienen del formulario (host, base, credenciales) viajan en la
    URL de conexión, no en esta sentencia.
    """
    values = ", ".join(f"('{schema}', '{table}')" for schema, table in _REQUIRED_TABLES)
    rows = (await conn.execute(text(_MISSING_TABLES_SQL.format(values=values)))).all()
    return tuple(f"{row[0]}.{row[1]}" for row in rows)


def _explain(error: Exception) -> str | None:
    """Traduce el fallo a algo accionable.

    El texto de asyncpg es correcto pero críptico para quien está
    cargando un formulario; acá se dice qué revisar.

    Devuelve `None` cuando el error no trae información suficiente para
    explicarlo y hace falta sondear — ver `_disambiguate`.
    """
    # `orig` es la excepción del driver cuando SQLAlchemy la envolvió;
    # si no la envolvió (fallo en la fase de conexión), es la propia.
    message = str(getattr(error, "orig", None) or error).lower()
    if "password authentication failed" in message:
        return "Usuario o contraseña incorrectos para esa base de datos."
    if "does not exist" in message:
        return "La base de datos no existe en ese servidor. Revisá el nombre."
    if "timeout" in message or "timed out" in message:
        return (
            "El servidor no respondió a tiempo. Revisá el host, el puerto y "
            "que el firewall permita la conexión."
        )
    if "closed in the middle of operation" in message:
        # Medido contra Postgres 16: asyncpg colapsa "la base no existe" y
        # "la contraseña está mal" en este mismo error, sin el detalle que
        # mandó el servidor. Hay que sondear para poder decir cuál fue.
        return None
    if "refused" in message or "connect" in message:
        return (
            "No se pudo conectar al servidor. Revisá el host y el puerto, y "
            "que PostgreSQL esté aceptando conexiones."
        )
    return "No se pudo conectar. Revisá los datos de conexión."


async def _disambiguate(database: ErpDatabase) -> str:
    """Distingue "credenciales mal" de "la base no existe".

    Reintenta contra la base de mantenimiento `postgres` con las mismas
    credenciales: si esa conecta, las credenciales sirven y el problema
    es el nombre de la base.

    Cuesta un intento extra y solo ocurre en el camino de fallo, nunca en
    el exitoso. Vale la pena: para quien está cargando el formulario, "te
    equivocaste en el nombre de la base" y "te equivocaste de contraseña"
    llevan a acciones distintas.
    """
    probe = replace(database, database="postgres")
    engine = _build_probe_engine(probe)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        return (
            "No se pudo conectar. Revisá el usuario y la contraseña, y que el "
            "servidor acepte conexiones desde este equipo."
        )
    else:
        return (
            f"El servidor responde y las credenciales son válidas, pero la base "
            f"'{database.database}' no existe ahí. Revisá el nombre."
        )
    finally:
        await engine.dispose()
