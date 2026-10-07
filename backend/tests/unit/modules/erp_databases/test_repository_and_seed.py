"""Tests del repositorio de bases del ERP, el seed y los índices únicos.

Corren contra una SQLite temporal real —no un fake— porque buena parte
de lo que se verifica ES el comportamiento del motor: los índices únicos
parciales y la persistencia del texto cifrado.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.config.settings import Settings
from app.infrastructure.database.base import Base
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.domain.exceptions import DuplicateErpDatabaseError
from app.modules.erp_databases.infrastructure.persistence import (
    ErpDatabaseModel,
    SqlAlchemyErpDatabaseRepository,
)
from app.modules.erp_databases.infrastructure.seed import seed_default_database
from app.shared.security import FernetCredentialCipher

_KEY = Fernet.generate_key().decode()
_OTHER_KEY = Fernet.generate_key().decode()


@pytest_asyncio.fixture
async def sessionmaker_(
    tmp_path: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'v.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[ErpDatabaseModel.__table__]
        )
    yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


def _repo(
    sm: async_sessionmaker[AsyncSession], key: str = _KEY
) -> SqlAlchemyErpDatabaseRepository:
    return SqlAlchemyErpDatabaseRepository(sm, FernetCredentialCipher(key))


def _database(**overrides: object) -> ErpDatabase:
    base = {
        "code": "NORTE",
        "name": "Cliente Norte",
        "host": "localhost",
        "port": 5432,
        "database": "erp_norte",
        "username": "postgres",
        "password": "s3cr3t",
    }
    base.update(overrides)
    return ErpDatabase(**base)  # type: ignore[arg-type]


# ── Cifrado en la frontera de persistencia ───────────────────────────


async def test_password_is_stored_encrypted_not_plain(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    await _repo(sessionmaker_).save(_database())

    async with sessionmaker_() as session:
        row = (await session.execute(ErpDatabaseModel.__table__.select())).first()
    assert row is not None
    stored = row._mapping["password_encrypted"]
    assert stored != "s3cr3t"
    assert "s3cr3t" not in stored


async def test_password_round_trips_through_repository(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    await repo.save(_database())

    loaded = await repo.get_by_code("NORTE")
    assert loaded is not None
    assert loaded.password == "s3cr3t"
    assert loaded.credentials_unreadable is False
    assert loaded.is_usable is True


async def test_wrong_key_marks_unreadable_instead_of_raising(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    """El escenario del `.env` restaurado de otro backup.

    La base queda inutilizable, pero listarla y arrancar la aplicación
    siguen funcionando: es la diferencia entre "re-cargá la contraseña" y
    un stacktrace de criptografía en el arranque.
    """
    await _repo(sessionmaker_).save(_database())

    loaded = await _repo(sessionmaker_, _OTHER_KEY).get_by_code("NORTE")

    assert loaded is not None
    assert loaded.credentials_unreadable is True
    assert loaded.password == ""
    assert loaded.is_usable is False


async def test_empty_password_on_update_keeps_the_stored_one(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    """El formulario de edición deja la contraseña vacía cuando no se
    quiere cambiar. Vacío = conservar, para no tener que devolverla al
    cliente y que la reenvíe."""
    repo = _repo(sessionmaker_)
    original = _database()
    await repo.save(original)

    edited = await repo.get_by_code("NORTE")
    assert edited is not None
    edited.name = "Cliente Norte S.A."
    edited.password = ""
    await repo.save(edited)

    reloaded = await repo.get_by_code("NORTE")
    assert reloaded is not None
    assert reloaded.name == "Cliente Norte S.A."
    assert reloaded.password == "s3cr3t"


# ── Búsqueda ─────────────────────────────────────────────────────────


async def test_get_by_code_is_case_insensitive(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    """`JPEREZ@norte` tiene que resolver igual que `@NORTE`: un login que
    falla por la caja sería indistinguible de una credencial mala."""
    repo = _repo(sessionmaker_)
    await repo.save(_database())

    assert await repo.get_by_code("norte") is not None
    assert await repo.get_by_code(" NoRtE ") is not None


async def test_get_by_code_ignores_deleted(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    database = _database()
    database.soft_delete()
    await repo.save(database)

    assert await repo.get_by_code("NORTE") is None


# ── Índices únicos parciales ─────────────────────────────────────────


async def test_duplicate_code_is_rejected(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    """El índice único parcial sobre `code`. Si no se creara, el síntoma
    no sería un error sino un login que resuelve la base equivocada.

    El repositorio traduce el `IntegrityError` del motor a la excepción
    de dominio (→ 422), en vez de dejar escapar un 500."""
    repo = _repo(sessionmaker_)
    await repo.save(_database())

    with pytest.raises(DuplicateErpDatabaseError):
        await repo.save(_database(name="Otro nombre"))


async def test_deleted_code_can_be_reused(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    """El único es PARCIAL: una base eliminada no bloquea registrar otra
    con el mismo código."""
    repo = _repo(sessionmaker_)
    first = _database()
    first.soft_delete()
    await repo.save(first)

    await repo.save(_database(name="Cliente Norte nuevo"))
    assert (await repo.get_by_code("NORTE")) is not None


async def test_two_defaults_are_rejected(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    await repo.save(_database(is_default=True))

    with pytest.raises(DuplicateErpDatabaseError):
        await repo.save(_database(code="SUR", name="Cliente Sur", is_default=True))


# ── Seed de arranque ─────────────────────────────────────────────────


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "agent_db_engine": "sqlite",
        "erp_db_host": "localhost",
        "erp_db_port": 5432,
        "erp_db_user": "postgres",
        "erp_db_password": "1234",
        "erp_db_name": "farmacias_similares",
        "erp_credentials_key": _KEY,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


async def test_seed_creates_the_default_database(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    await seed_default_database(repo, _settings())

    default = await repo.get_default()
    assert default is not None
    assert default.database == "farmacias_similares"
    assert default.password == "1234"
    assert default.is_default is True
    assert default.is_active is True


async def test_seed_is_idempotent(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    await seed_default_database(repo, _settings())
    await seed_default_database(repo, _settings())

    assert await repo.count() == 1


async def test_seed_does_not_resurrect_a_deleted_database(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    """`count()` incluye las eliminadas a propósito: si el administrador
    dio de baja la base sembrada, el arranque no debe volver a crearla."""
    repo = _repo(sessionmaker_)
    await seed_default_database(repo, _settings())
    seeded = await repo.get_default()
    assert seeded is not None
    seeded.soft_delete()
    await repo.save(seeded)

    await seed_default_database(repo, _settings())

    assert await repo.count() == 1
    assert await repo.get_default() is None


async def test_seed_without_erp_config_does_nothing(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    """Sin ERP en el `.env` no es un error: la primera base se puede
    registrar desde la sección de administración."""
    repo = _repo(sessionmaker_)
    await seed_default_database(repo, _settings(erp_db_host="", erp_db_name=""))

    assert await repo.count() == 0


# ── Revisión del seed (reconfigurar desde el instalador) ─────────────


async def test_fresh_seed_stores_the_revision(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    await seed_default_database(repo, _settings(erp_seed_revision="20260101000000"))

    default = await repo.get_default()
    assert default is not None
    assert default.seed_revision == "20260101000000"


async def test_same_revision_preserves_admin_edits(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    settings = _settings(erp_seed_revision="r1")
    await seed_default_database(repo, settings)
    edited = await repo.get_default()
    assert edited is not None
    edited.host = "editado-por-admin"
    await repo.save(edited)

    await seed_default_database(repo, settings)

    default = await repo.get_default()
    assert default is not None
    assert default.host == "editado-por-admin"


async def test_new_revision_updates_connection_and_reencrypts_password(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    await seed_default_database(repo, _settings(erp_seed_revision="r1"))
    before = await repo.get_default()
    assert before is not None
    async with sessionmaker_() as session:
        old_cipher = (await session.execute(ErpDatabaseModel.__table__.select())).first()
    assert old_cipher is not None

    await seed_default_database(
        repo,
        _settings(
            erp_seed_revision="r2",
            erp_db_host="otro-host",
            erp_db_port=6543,
            erp_db_name="otra_base",
            erp_db_user="otro_user",
            erp_db_password="nueva-clave",
        ),
    )

    after = await repo.get_default()
    assert after is not None
    assert after.id == before.id
    assert (after.host, after.port, after.database, after.username) == (
        "otro-host",
        6543,
        "otra_base",
        "otro_user",
    )
    assert after.password == "nueva-clave"
    assert after.seed_revision == "r2"
    assert after.name == before.name and after.code == before.code
    assert await repo.count() == 1
    async with sessionmaker_() as session:
        new_cipher = (await session.execute(ErpDatabaseModel.__table__.select())).first()
    assert new_cipher is not None
    assert (
        new_cipher._mapping["password_encrypted"] != old_cipher._mapping["password_encrypted"]
    )


async def test_empty_revision_leaves_the_seeded_database_untouched(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    repo = _repo(sessionmaker_)
    await seed_default_database(repo, _settings(erp_seed_revision="r1"))

    await seed_default_database(
        repo, _settings(erp_seed_revision="", erp_db_host="otro-host")
    )

    default = await repo.get_default()
    assert default is not None
    assert default.host == "localhost"
    assert default.seed_revision == "r1"
