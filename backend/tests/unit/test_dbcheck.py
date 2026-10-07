"""`savi-dbcheck` contra el Postgres real de desarrollo.

Cada caso es un error que un técnico puede cometer al cargar el asistente,
y lo que se verifica es que el mensaje diga QUÉ revisar. Se salta si no hay
un Postgres alcanzable con los datos de `.env`. Crea y borra sus propias
bases y roles.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.dbcheck import DbRequest, check, main, parse_request
from app.infrastructure.config import get_settings
from app.infrastructure.database.create_database import (
    _maintenance_url,  # pyright: ignore[reportPrivateUsage]
)


def _request(**overrides: object) -> DbRequest:
    s = get_settings()
    base: dict[str, object] = {
        "kind": "savi",
        "host": s.agent_db_host or "localhost",
        "port": s.agent_db_port,
        "database": s.agent_db_name or "savi",
        "user": s.agent_db_user or "postgres",
        "password": s.agent_db_password or "",
        "new_key": False,
    }
    return DbRequest(**{**base, **overrides})  # pyright: ignore[reportArgumentType]


@pytest_asyncio.fixture
async def admin() -> AsyncIterator[AsyncEngine]:
    settings = get_settings().model_copy(update={"agent_db_engine": "postgresql"})
    engine = create_async_engine(
        _maintenance_url(settings, "postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as error:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"No hay Postgres alcanzable: {error}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def limited_role(admin: AsyncEngine) -> AsyncIterator[str]:
    role = f"test_dbcheck_{uuid4().hex[:8]}"
    async with admin.connect() as connection:
        await connection.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD 'x-test' NOCREATEDB"))
    yield role
    async with admin.connect() as connection:
        await connection.execute(text(f"DROP ROLE IF EXISTS {role}"))


async def test_wrong_password_says_user_or_password(admin: AsyncEngine) -> None:
    outcome = await check(_request(password="definitivamente-mala"))

    assert outcome.level == "error" and "contraseña incorrectos" in outcome.message


async def test_wrong_port_names_the_port(admin: AsyncEngine) -> None:
    outcome = await check(_request(port=5999))

    assert outcome.level == "error" and "puerto 5999" in outcome.message


async def test_unknown_host_names_the_server() -> None:
    outcome = await check(_request(host="servidor-que-no-existe.local"))

    assert outcome.level == "error" and "No se encontró el servidor" in outcome.message


async def test_missing_database_is_created_later_when_the_user_can(admin: AsyncEngine) -> None:
    outcome = await check(_request(database=f"savi_nueva_{uuid4().hex[:8]}"))

    assert outcome.level == "ok" and "SAVI la crea" in outcome.message


async def test_missing_database_without_createdb_says_what_to_ask(limited_role: str) -> None:
    outcome = await check(
        _request(database=f"savi_nueva_{uuid4().hex[:8]}", user=limited_role, password="x-test")
    )

    assert outcome.level == "error" and "CREATE DATABASE" in outcome.message


async def test_existing_database_without_create_permission_says_grant(
    admin: AsyncEngine, limited_role: str
) -> None:
    name = f"test_dbcheck_db_{uuid4().hex[:8]}"
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    settings = get_settings().model_copy(update={"agent_db_engine": "postgresql"})
    target = create_async_engine(_maintenance_url(settings, name), isolation_level="AUTOCOMMIT")
    try:
        async with target.connect() as connection:
            # Como en PostgreSQL 15+, explícito para que valga en cualquier versión.
            await connection.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
        await target.dispose()

        outcome = await check(_request(database=name, user=limited_role, password="x-test"))

        assert outcome.level == "error" and "GRANT CREATE ON SCHEMA public" in outcome.message
    finally:
        await target.dispose()
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


async def test_an_empty_database_is_ready(admin: AsyncEngine) -> None:
    name = f"test_dbcheck_db_{uuid4().hex[:8]}"
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        outcome = await check(_request(database=name))

        assert outcome.level == "ok" and "vacía" in outcome.message
    finally:
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


async def test_erp_check_rejects_a_database_that_is_not_the_erp(admin: AsyncEngine) -> None:
    outcome = await check(_request(kind="erp"))

    assert outcome.level == "aviso" and "no parece la del ERP" in outcome.message


def test_the_request_file_keeps_the_password_verbatim() -> None:
    request = parse_request(["savi", " srv ", "5433", "savi", "postgres", " a=b c ", "0"])

    assert request.host == "srv" and request.port == 5433
    assert request.password == " a=b c " and request.new_key is False


def test_main_writes_level_and_message_and_returns_its_code(tmp_path: Path) -> None:
    request_file = tmp_path / "pedido.txt"
    result_file = tmp_path / "resultado.txt"
    request_file.write_text(
        "savi\nservidor-que-no-existe.local\n5432\nsavi\npostgres\nx\n1\n", encoding="utf-8-sig"
    )

    code = main(["savi-dbcheck", str(request_file), str(result_file)])

    level, message = result_file.read_text(encoding="mbcs").split("\n", 1)
    assert code == 2 and level == "error" and "servidor-que-no-existe.local" in message
