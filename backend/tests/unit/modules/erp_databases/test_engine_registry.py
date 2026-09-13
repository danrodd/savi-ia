"""Tests del registry de engines y del value object del código.

El registry no abre conexiones reales en estos tests: `create_async_engine`
es diferido, así que se puede verificar la administración del ciclo de
vida (cacheo, LRU, invalidación) sin un Postgres levantado.
"""
from __future__ import annotations

import pytest

from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.domain.value_objects import (
    InvalidDatabaseCodeError,
    normalize_code,
)
from app.modules.erp_databases.infrastructure.engine_registry import ErpEngineRegistry


def _database(code: str) -> ErpDatabase:
    return ErpDatabase(
        code=code,
        name=f"Cliente {code}",
        host="localhost",
        port=5432,
        database=f"erp_{code.lower()}",
        username="postgres",
        password="pass",
    )


# ── Registry ─────────────────────────────────────────────────────────


async def test_same_database_reuses_the_engine() -> None:
    """Sin cacheo, cada turno abriría un pool nuevo contra la BD del
    cliente y los anteriores quedarían huérfanos."""
    registry = ErpEngineRegistry()
    database = _database("NORTE")

    assert await registry.get(database) is await registry.get(database)
    await registry.dispose_all()


async def test_different_databases_get_different_engines() -> None:
    registry = ErpEngineRegistry()

    engine_a = await registry.get(_database("NORTE"))
    engine_b = await registry.get(_database("SUR"))

    assert engine_a is not engine_b
    await registry.dispose_all()


async def test_invalidate_forces_a_new_engine() -> None:
    """Es lo que hace que cambiar una contraseña tenga efecto sin
    reiniciar el proceso."""
    registry = ErpEngineRegistry()
    database = _database("NORTE")
    first = await registry.get(database)

    await registry.invalidate(database.id)

    assert await registry.get(database) is not first
    await registry.dispose_all()


async def test_invalidate_is_idempotent() -> None:
    registry = ErpEngineRegistry()
    database = _database("NORTE")

    await registry.invalidate(database.id)  # nunca se abrió
    await registry.get(database)
    await registry.invalidate(database.id)
    await registry.invalidate(database.id)  # ya no está

    await registry.dispose_all()


async def test_lru_eviction_respects_the_cap() -> None:
    """El tope acota las conexiones sin importar cuántas bases haya
    registradas."""
    registry = ErpEngineRegistry(max_engines=2)
    a, b, c = _database("A"), _database("B"), _database("C")

    engine_a = await registry.get(a)
    await registry.get(b)
    await registry.get(c)  # expulsa a `a`, el menos usado

    assert len(registry._engines) == 2
    assert await registry.get(a) is not engine_a
    await registry.dispose_all()


async def test_reuse_refreshes_lru_position() -> None:
    """Usar una base la protege de la evicción: un agente que alterna
    entre dos clientes no debe perder el engine de ninguno."""
    registry = ErpEngineRegistry(max_engines=2)
    a, b, c = _database("A"), _database("B"), _database("C")

    engine_a = await registry.get(a)
    await registry.get(b)
    await registry.get(a)  # `a` vuelve a ser el más reciente
    await registry.get(c)  # ahora el candidato a salir es `b`

    assert await registry.get(a) is engine_a
    await registry.dispose_all()


# ── URL de conexión ──────────────────────────────────────────────────


def test_url_escapes_special_characters_in_credentials() -> None:
    """Una contraseña con `@` o `/` es válida en Postgres pero rompería
    el parseo de la URL, con un error de conexión indescifrable."""
    database = _database("NORTE")
    database.username = "user@corp"
    database.password = "p@ss/word:1"

    url = database.url

    assert "user%40corp" in url
    assert "p%40ss%2Fword%3A1" in url
    assert url.endswith("@localhost:5432/erp_norte")


# ── Código del cliente ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("norte", "NORTE"), ("  sur  ", "SUR"), ("cli-01", "CLI-01"), ("a_b", "A_B")],
)
def test_normalize_code_uppercases_and_trims(raw: str, expected: str) -> None:
    assert normalize_code(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "a",  # muy corto
        "x" * 33,  # muy largo
        "con espacio",
        "tiene@arroba",  # rompería el rsplit del login
        "acentué",
        None,
    ],
)
def test_invalid_codes_are_rejected(raw: object) -> None:
    with pytest.raises(InvalidDatabaseCodeError):
        normalize_code(raw)
