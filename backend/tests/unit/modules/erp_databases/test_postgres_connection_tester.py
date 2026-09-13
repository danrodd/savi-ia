"""`PostgresConnectionTester` contra un Postgres real.

Es el único test de la suite que depende de un Postgres real: la
verificación de esquema (D5 paso 3) usa `information_schema`, y
simularla fiel con SQLite no es posible (los nombres de tabla con
mayúsculas entre comillas, el catálogo, todo es específico de Postgres).
Los demás tests de `erp_databases` prueban la lógica de negocio con un
`ConnectionTester` falso — este prueba la implementación real.

Se salta si no hay un Postgres alcanzable en `localhost:5432` con
`postgres`/`1234` (el de este entorno de desarrollo) — no bloquea CI ni
a quien no tenga uno corriendo. Crea y borra su propia base de prueba;
no toca `savi_agente` ni ninguna base de un cliente.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.infrastructure.postgres_connection_tester import (
    PostgresConnectionTester,
)

_HOST = "localhost"
_PORT = 5432
_USER = "postgres"
_PASSWORD = "1234"


async def _admin_connection() -> asyncpg.Connection:
    return await asyncpg.connect(
        host=_HOST, port=_PORT, user=_USER, password=_PASSWORD,
        database="postgres", timeout=3,
    )


@pytest_asyncio.fixture
async def temp_database() -> AsyncIterator[str]:
    try:
        admin = await _admin_connection()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"No hay Postgres alcanzable en {_HOST}:{_PORT}: {e}")
    name = f"test_erp_schema_{uuid4().hex[:12]}"
    await admin.execute(f'CREATE DATABASE "{name}"')
    await admin.close()
    try:
        yield name
    finally:
        admin = await _admin_connection()
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


def _database(name: str) -> ErpDatabase:
    return ErpDatabase(
        code="TEST",
        name="Cliente de prueba",
        host=_HOST,
        port=_PORT,
        database=name,
        username=_USER,
        password=_PASSWORD,
        statement_timeout_ms=60000,
    )


async def test_rejects_a_postgres_without_the_erp_schema(temp_database: str) -> None:
    """Una base vacía conecta pero no es un ERP de SEO: D5 tiene que
    rechazarla con el detalle de qué tablas faltan, no dejar pasar
    cualquier Postgres."""
    tester = PostgresConnectionTester()

    result = await tester.test(_database(temp_database))

    assert result.ok is False
    assert "Seguridad.Usuario" in result.missing_tables
    assert "Empresa.Empresa" in result.missing_tables
    assert result.razon_social is None


async def test_accepts_a_postgres_with_the_required_schema(temp_database: str) -> None:
    """Con las cinco tablas requeridas presentes, D5 acepta la base y
    propone la razón social leída de `Empresa.Empresa`."""
    conn = await asyncpg.connect(
        host=_HOST, port=_PORT, user=_USER, password=_PASSWORD,
        database=temp_database, timeout=3,
    )
    try:
        await conn.execute('CREATE SCHEMA "Seguridad"')
        await conn.execute('CREATE TABLE "Seguridad"."Usuario" (id int)')
        await conn.execute('CREATE TABLE "Seguridad"."Formulario" (id int)')
        await conn.execute('CREATE TABLE "Seguridad"."PermisoFormulario" (id int)')
        await conn.execute('CREATE SCHEMA "SEO"')
        await conn.execute('CREATE TABLE "SEO"."Modulo" (id int)')
        await conn.execute('CREATE SCHEMA "Empresa"')
        await conn.execute(
            'CREATE TABLE "Empresa"."Empresa" ("idEmpresa" int, "razonSocial" text)'
        )
        await conn.execute(
            """INSERT INTO "Empresa"."Empresa" VALUES (1, 'ACME SAS')"""
        )
    finally:
        await conn.close()

    tester = PostgresConnectionTester()
    result = await tester.test(_database(temp_database))

    assert result.ok is True
    assert result.razon_social == "ACME SAS"
    assert result.missing_tables == ()


async def test_wrong_password_is_reported_without_leaking_it(temp_database: str) -> None:
    """Un dato de conexión equivocado es entrada mal cargada: `ok=False`
    con un mensaje accionable, nunca una excepción ni la contraseña en
    el detalle."""
    tester = PostgresConnectionTester()
    bad = _database(temp_database)
    bad.password = "claramente-mal"

    result = await tester.test(bad)

    assert result.ok is False
    assert "claramente-mal" not in result.detail
