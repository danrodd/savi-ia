"""Prueba de conexión a PostgreSQL para el instalador (`savi-dbcheck.exe`).

El asistente de instalación lo usa en el botón "Probar conexión" y al
pasar de página, antes de copiar SAVI: así un dato mal cargado se corrige
en el momento, con un mensaje que dice QUÉ está mal (servidor, puerto,
usuario, contraseña, base o permisos), y no recién al abrir SAVI.

Es un ejecutable aparte y chico a propósito: el instalador lo extrae a un
temporal antes de instalar nada, y el bundle de SAVI pesa cientos de MB.

Uso: savi-dbcheck <pedido> <resultado>

- pedido (UTF-8, una línea por campo): tipo (`erp` | `savi`), servidor,
  puerto, base, usuario, contraseña, clave nueva (`1` | `0`). Va en un
  archivo y no en la línea de comandos para que la contraseña no quede
  visible en la lista de procesos.
- resultado (ANSI, lo que lee Inno Setup): primera línea `ok` | `aviso` |
  `error`; el resto, el mensaje para el técnico.
- código de salida: 0 ok, 1 aviso, 2 error.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

Level = Literal["ok", "aviso", "error"]
Kind = Literal["erp", "savi"]

_CONNECT_TIMEOUT_SECONDS = 8
# Bases que existen en todo servidor; sirven para separar "la base no
# existe" de "el usuario o la contraseña están mal" cuando el driver no
# trae el motivo.
_MAINTENANCE_DATABASES = ("postgres", "template1")
# Mismas tablas que exige el alta de bases del ERP (PostgresConnectionTester).
_ERP_TABLES: tuple[tuple[str, str], ...] = (
    ("Seguridad", "Usuario"),
    ("Seguridad", "Formulario"),
    ("Seguridad", "PermisoFormulario"),
    ("SEO", "Modulo"),
    ("Empresa", "Empresa"),
)
_EXIT_CODES: dict[Level, int] = {"ok": 0, "aviso": 1, "error": 2}


@dataclass(frozen=True, slots=True)
class DbRequest:
    kind: Kind
    host: str
    port: int
    database: str
    user: str
    password: str
    # La instalación genera una clave de cifrado nueva (no reutiliza la de
    # un .env anterior): las credenciales que ya guarda una base de SAVI
    # existente no se van a poder leer.
    new_key: bool = True


@dataclass(frozen=True, slots=True)
class Outcome:
    level: Level
    message: str


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _url(request: DbRequest, database: str) -> URL:
    return URL.create(
        "postgresql+asyncpg",
        username=request.user,
        password=request.password,
        host=request.host,
        port=request.port,
        database=database,
    )


def _root_cause(error: BaseException) -> BaseException:
    """La excepción del driver, debajo de los envoltorios de SQLAlchemy."""
    seen: set[int] = set()
    current = error
    while id(current) not in seen:
        seen.add(id(current))
        inner = getattr(current, "orig", None) or current.__cause__
        if not isinstance(inner, BaseException):
            break
        current = inner
    return current


async def _try_connect(request: DbRequest, database: str) -> BaseException | None:
    engine = create_async_engine(
        _url(request, database), connect_args={"timeout": _CONNECT_TIMEOUT_SECONDS}
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as error:  # noqa: BLE001 - se clasifica abajo
        return _root_cause(error)
    finally:
        await engine.dispose()
    return None


def _explain_connection_error(request: DbRequest, error: BaseException) -> Outcome | None:
    """Traduce el fallo. `None` = no se sabe todavía si falta la base o
    fallaron las credenciales: con el servidor en español, asyncpg corta la
    conexión sin el motivo ("connection was closed in the middle of
    operation") en los dos casos."""
    server = f"{request.host}:{request.port}"
    if isinstance(error, socket.gaierror):
        return Outcome(
            "error",
            f"No se encontró el servidor '{request.host}'. Revisá que el nombre o la "
            "IP estén bien escritos y que este equipo llegue a esa red.",
        )
    if isinstance(error, ConnectionRefusedError):
        return Outcome(
            "error",
            f"El servidor '{request.host}' no acepta conexiones en el puerto "
            f"{request.port}. Revisá el puerto (PostgreSQL usa 5432 por defecto) y que "
            "el servicio de PostgreSQL esté iniciado.",
        )
    if _is_dropped_connection(error):
        return None
    # asyncpg cancela la conexión al vencer el timeout: llega como CancelledError.
    if isinstance(error, TimeoutError | asyncio.CancelledError):
        return Outcome(
            "error",
            f"{server} no respondió a tiempo. Revisá el servidor y el puerto, y que el "
            "firewall permita la conexión desde este equipo.",
        )
    sqlstate = getattr(error, "sqlstate", None)
    if sqlstate == "28P01":
        return Outcome(
            "error",
            f"Usuario o contraseña incorrectos para '{request.user}' en {server}.",
        )
    if sqlstate == "28000":
        return Outcome(
            "error",
            f"El servidor rechazó al usuario '{request.user}': no existe, o el servidor "
            "no permite conexiones desde este equipo (pg_hba.conf).",
        )
    if sqlstate == "3D000":
        return None
    if isinstance(error, OSError):
        return Outcome(
            "error",
            f"No se pudo llegar a {server}: {error}. Revisá el servidor, el puerto y la red.",
        )
    return Outcome("error", f"No se pudo conectar a {server}: {type(error).__name__}: {error}")


# WinError 64 ("el nombre de red ya no está disponible") y 10054
# ("conexión reiniciada"): así llega a Windows el corte del servidor cuando
# asyncpg no pudo leer su mensaje de error.
_DROPPED_CONNECTION_WINERRORS = frozenset({64, 10054})


def _is_dropped_connection(error: BaseException) -> bool:
    if type(error).__name__ == "ConnectionDoesNotExistError":
        return True
    if isinstance(error, ConnectionResetError):
        return True
    return getattr(error, "winerror", None) in _DROPPED_CONNECTION_WINERRORS


async def check(request: DbRequest) -> Outcome:
    error = await _try_connect(request, request.database)
    if error is None:
        return await _inspect_existing(request)

    explained = _explain_connection_error(request, error)
    if explained is not None:
        return explained

    # Ambiguo: si la base de mantenimiento conecta con las mismas
    # credenciales, el problema es que la base pedida no existe.
    for maintenance in _MAINTENANCE_DATABASES:
        maintenance_error = await _try_connect(request, maintenance)
        if maintenance_error is None:
            return await _missing_database(request, maintenance)
        explained = _explain_connection_error(request, maintenance_error)
        if explained is not None:
            return explained
    return Outcome(
        "error",
        f"Usuario o contraseña incorrectos para '{request.user}', o el servidor no "
        "permite conexiones desde este equipo (pg_hba.conf).",
    )


async def _missing_database(request: DbRequest, maintenance: str) -> Outcome:
    if request.kind == "erp":
        return Outcome(
            "error",
            f"El servidor responde y el usuario es válido, pero la base "
            f"'{request.database}' no existe. Revisá el nombre de la base del ERP.",
        )
    engine = create_async_engine(
        _url(request, maintenance), connect_args={"timeout": _CONNECT_TIMEOUT_SECONDS}
    )
    try:
        async with engine.connect() as connection:
            can_create = await connection.scalar(
                text("SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = current_user")
            )
    finally:
        await engine.dispose()
    if can_create:
        return Outcome(
            "ok",
            f"Conexión correcta. La base '{request.database}' no existe todavía: SAVI "
            "la crea al terminar la instalación.",
        )
    return Outcome(
        "error",
        f"La base '{request.database}' no existe y el usuario '{request.user}' no tiene "
        "permiso para crearla. Pedile al administrador del servidor que la cree "
        f"(CREATE DATABASE {_quote_identifier(request.database)} OWNER "
        f"{_quote_identifier(request.user)};) o usá un usuario con permiso CREATEDB.",
    )


async def _inspect_existing(request: DbRequest) -> Outcome:
    engine = create_async_engine(
        _url(request, request.database), connect_args={"timeout": _CONNECT_TIMEOUT_SECONDS}
    )
    try:
        async with engine.connect() as connection:
            if request.kind == "erp":
                return await _inspect_erp(connection)
            return await _inspect_savi(connection, request)
    finally:
        await engine.dispose()


async def _inspect_erp(connection: AsyncConnection) -> Outcome:
    missing: list[str] = []
    unreadable: list[str] = []
    for schema, table in _ERP_TABLES:
        qualified = f"{_quote_identifier(schema)}.{_quote_identifier(table)}"
        exists = await connection.scalar(text("SELECT to_regclass(:t)"), {"t": qualified})
        if exists is None:
            missing.append(f"{schema}.{table}")
            continue
        readable = await connection.scalar(
            text("SELECT has_table_privilege(:t, 'SELECT')"), {"t": qualified}
        )
        if not readable:
            unreadable.append(f"{schema}.{table}")
    if missing:
        return Outcome(
            "aviso",
            "La conexión funciona, pero esta base no parece la del ERP de SEO (faltan "
            f"{', '.join(missing)}). Revisá el nombre de la base.",
        )
    if unreadable:
        return Outcome(
            "error",
            "La conexión funciona, pero el usuario no tiene permiso de lectura sobre "
            f"{', '.join(unreadable)}. SAVI necesita poder leer la base del ERP.",
        )
    company = await connection.scalar(
        text('SELECT "razonSocial" FROM "Empresa"."Empresa" ORDER BY "idEmpresa" LIMIT 1')
    )
    suffix = f" Empresa: {company}." if company else ""
    return Outcome("ok", f"Conexión correcta con la base del ERP.{suffix}")


async def _inspect_savi(connection: AsyncConnection, request: DbRequest) -> Outcome:
    can_create_tables = bool(
        await connection.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'public') "
                "AND has_schema_privilege('public', 'CREATE')"
            )
        )
    )
    if not can_create_tables:
        return Outcome(
            "error",
            f"La base existe, pero el usuario '{request.user}' no puede crear tablas en "
            "ella (desde PostgreSQL 15 hace falta un permiso explícito). Pedile al "
            "administrador: GRANT CREATE ON SCHEMA public TO "
            f"{_quote_identifier(request.user)}; o que lo haga dueño de la base.",
        )
    is_savi = await connection.scalar(text("SELECT to_regclass('public.alembic_version')"))
    table_count = int(
        await connection.scalar(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
            )
        )
        or 0
    )
    if is_savi is not None:
        return await _describe_savi_data(connection, request)
    if table_count:
        return Outcome(
            "aviso",
            f"La base '{request.database}' ya tiene {table_count} tablas que no son de "
            "SAVI. SAVI no las borra, pero conviene una base propia (por ejemplo "
            "'savi'): mezclar datos complica los respaldos y las actualizaciones.",
        )
    return Outcome("ok", "Conexión correcta. La base está vacía: SAVI crea las tablas al arrancar.")


async def _count(connection: AsyncConnection, sql: str) -> int:
    """Cuenta filas de una tabla que puede no existir en versiones viejas."""
    try:
        async with connection.begin_nested():
            return int(await connection.scalar(text(sql)) or 0)
    except Exception:  # noqa: BLE001 - tabla ausente: cuenta como cero
        return 0


async def _describe_savi_data(connection: AsyncConnection, request: DbRequest) -> Outcome:
    conversations = await _count(
        connection, "SELECT count(*) FROM conversations WHERE deleted_at IS NULL"
    )
    credentials = await _count(connection, "SELECT count(*) FROM erp_databases") + await _count(
        connection,
        "SELECT count(*) FROM llm_provider_configs WHERE credential_encrypted IS NOT NULL",
    )
    message = (
        f"Conexión correcta. La base '{request.database}' ya tiene datos de SAVI "
        f"({conversations} conversaciones). Se conservan: instalar o reconfigurar "
        "no borra nada."
    )
    if request.new_key and credentials:
        return Outcome(
            "aviso",
            message + " Ojo: también guarda credenciales (bases del ERP o proveedores de "
            "IA) cifradas con la clave de otra instalación. Si esta base la usa otro "
            "equipo, copiá ERP_CREDENTIALS_KEY de su archivo .env a este después de "
            "instalar; si no, esas credenciales hay que volver a cargarlas.",
        )
    return Outcome("ok", message)


def parse_request(lines: list[str]) -> DbRequest:
    fields = [line.rstrip("\r\n") for line in lines]
    if len(fields) < 6 or fields[0] not in ("erp", "savi"):
        raise ValueError("pedido incompleto")
    kind: Kind = "erp" if fields[0] == "erp" else "savi"
    return DbRequest(
        kind=kind,
        host=fields[1].strip(),
        port=int(fields[2].strip()),
        database=fields[3].strip(),
        user=fields[4].strip(),
        password=fields[5],
        new_key=(fields[6].strip() != "0") if len(fields) > 6 else True,
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    request_path, result_path = Path(argv[1]), Path(argv[2])
    try:
        request = parse_request(request_path.read_text(encoding="utf-8-sig").splitlines())
        outcome = asyncio.run(check(request))
    except Exception as error:  # noqa: BLE001 - todo fallo se le informa al técnico
        outcome = Outcome("error", f"No se pudo probar la conexión: {error}")
    # ANSI y no UTF-8: es lo que lee `LoadStringFromFile` de Inno Setup.
    result_path.write_text(
        f"{outcome.level}\n{outcome.message}\n", encoding="mbcs", errors="replace"
    )
    return _EXIT_CODES[outcome.level]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
