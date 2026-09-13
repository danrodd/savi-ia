"""Export/import de bases del ERP entre dos instalaciones distintas.

El escenario real: un call center con varios agentes, cada uno con su
propia instalación de escritorio (su propia `ERP_CREDENTIALS_KEY`,
aleatoria). Estos tests arman DOS repositorios independientes — "A" (el
que exporta) y "B" (el que importa) — cada uno con su propia clave
Fernet, para probar exactamente eso: que la contraseña viaja re-cifrada
con la clave de B, no con la de A.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.erp_databases.application.dtos import SaveErpDatabaseDTO
from app.modules.erp_databases.application.use_cases import (
    ExportImportErpDatabasesUseCase,
    ManageErpDatabasesUseCase,
)
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.domain.exceptions import InvalidExportPassphraseError
from app.modules.erp_databases.domain.interfaces.connection_tester import (
    ConnectionTester,
    ConnectionTestResult,
)
from app.modules.erp_databases.infrastructure.engine_registry import ErpEngineRegistry
from app.modules.erp_databases.infrastructure.persistence import (
    SqlAlchemyErpDatabaseRepository,
)
from app.modules.erp_databases.infrastructure.security import FernetCredentialCipher
from app.shared.exceptions import ValidationError

_PASSPHRASE = "clave-compartida-del-call-center"

_Installation = tuple[ManageErpDatabasesUseCase, ExportImportErpDatabasesUseCase]


class _FakeTester(ConnectionTester):
    """Conecta a todo salvo lo que esté en `unreachable` — simula que un
    agente puede no alcanzar la red de un cliente en particular."""

    def __init__(self, unreachable: set[str] | None = None) -> None:
        self.unreachable = unreachable or set()

    async def test(self, database: ErpDatabase) -> ConnectionTestResult:
        if database.database in self.unreachable:
            return ConnectionTestResult(ok=False, detail="No se pudo conectar.")
        return ConnectionTestResult(ok=True, detail="ok", razon_social="ACME SA")


async def _installation(
    tmp_path: Path, name: str, *, unreachable: set[str] | None = None
) -> AsyncIterator[_Installation]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / name).as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    # Cada instalación tiene su PROPIA clave Fernet — el punto central
    # del feature es que no hace falta compartirla.
    cipher = FernetCredentialCipher(Fernet.generate_key().decode())
    repo = SqlAlchemyErpDatabaseRepository(sm, cipher)
    manager = ManageErpDatabasesUseCase(repo, _FakeTester(unreachable), ErpEngineRegistry())
    export_import = ExportImportErpDatabasesUseCase(repo, manager)
    yield manager, export_import
    await engine.dispose()


@pytest_asyncio.fixture
async def installation_a(tmp_path: Path):
    async for pair in _installation(tmp_path, "a.db"):
        yield pair


def _dto(**overrides: object) -> SaveErpDatabaseDTO:
    base: dict[str, object] = {
        "code": "NORTE", "name": "Cliente Norte", "host": "localhost", "port": 5432,
        "database": "erp_norte", "username": "postgres", "password": "s3cr3t",
    }
    base.update(overrides)
    return SaveErpDatabaseDTO(**base)  # type: ignore[arg-type]


async def test_round_trips_into_a_fresh_installation(
    tmp_path: Path, installation_a: _Installation
) -> None:
    manager_a, export_a = installation_a
    await manager_a.create(_dto(code="NORTE"))
    await manager_a.create(_dto(code="SUR", name="Cliente Sur", database="erp_sur"))
    await manager_a.set_default((await manager_a.list())[1].id)  # SUR es la default en A

    payload = await export_a.export(_PASSPHRASE)
    assert payload.count == 2

    async for manager_b, import_b in _installation(tmp_path, "b.db"):
        result = await import_b.import_(_PASSPHRASE, payload.ciphertext)

        assert {r.code: r.status for r in result.rows} == {"NORTE": "created", "SUR": "created"}
        listed = {d.code: d for d in await manager_b.list()}
        assert listed["NORTE"].host == "localhost"
        assert listed["SUR"].is_default is True
        assert listed["NORTE"].is_default is False


async def test_existing_code_gets_updated_not_duplicated(
    tmp_path: Path, installation_a: _Installation
) -> None:
    """El caso que motiva el feature: la IP de un cliente cambió, y hay
    que propagar eso a todos los agentes sin tocarlos uno por uno."""
    manager_a, export_a = installation_a
    await manager_a.create(_dto(code="NORTE", host="ip-nueva.cliente.com"))
    payload = await export_a.export(_PASSPHRASE)

    async for manager_b, import_b in _installation(tmp_path, "b.db"):
        existing = await manager_b.create(_dto(code="NORTE", host="ip-vieja.cliente.com"))

        result = await import_b.import_(_PASSPHRASE, payload.ciphertext)

        assert len(result.rows) == 1
        assert result.rows[0].code == "NORTE"
        assert result.rows[0].status == "updated"
        updated = await manager_b.get(existing.id)
        assert updated.host == "ip-nueva.cliente.com"


async def test_unreachable_database_fails_without_blocking_the_rest(
    tmp_path: Path, installation_a: _Installation
) -> None:
    """Best-effort por fila: agentes en redes distintas pueden no
    alcanzar todos los clientes."""
    manager_a, export_a = installation_a
    await manager_a.create(_dto(code="NORTE"))
    await manager_a.create(_dto(code="SUR", name="Cliente Sur", database="erp_sur"))
    payload = await export_a.export(_PASSPHRASE)

    async for manager_b, import_b in _installation(tmp_path, "b.db", unreachable={"erp_sur"}):
        result = await import_b.import_(_PASSPHRASE, payload.ciphertext)

        statuses = {r.code: r.status for r in result.rows}
        assert statuses["NORTE"] == "created"
        assert statuses["SUR"] == "failed"
        assert [d.code for d in await manager_b.list()] == ["NORTE"]


async def test_wrong_passphrase_is_rejected(
    tmp_path: Path, installation_a: _Installation
) -> None:
    manager_a, export_a = installation_a
    await manager_a.create(_dto())
    payload = await export_a.export(_PASSPHRASE)

    async for _manager_b, import_b in _installation(tmp_path, "b.db"):
        with pytest.raises(InvalidExportPassphraseError):
            await import_b.import_("contraseña-equivocada", payload.ciphertext)


async def test_export_requires_a_passphrase(
    installation_a: _Installation,
) -> None:
    _manager_a, export_a = installation_a

    with pytest.raises(ValidationError):
        await export_a.export("")


async def test_export_omits_databases_with_unreadable_credentials(
    tmp_path: Path,
) -> None:
    """Sin contraseña legible no hay nada que exportar para esa fila —
    exportar un password vacío rompería silenciosamente el alta en
    destino."""
    db_path = tmp_path / "unreadable.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    original_key = Fernet.generate_key().decode()
    repo = SqlAlchemyErpDatabaseRepository(sm, FernetCredentialCipher(original_key))
    manager = ManageErpDatabasesUseCase(repo, _FakeTester(), ErpEngineRegistry())
    await manager.create(_dto())

    # Otra instancia sobre el MISMO archivo, con una clave distinta:
    # simula la clave de cifrado perdida/cambiada — igual que si esta
    # fuera una instalación real que restauró un `.env` viejo.
    other_key_repo = SqlAlchemyErpDatabaseRepository(
        sm, FernetCredentialCipher(Fernet.generate_key().decode())
    )
    other_manager = ManageErpDatabasesUseCase(
        other_key_repo, _FakeTester(), ErpEngineRegistry()
    )
    export_with_bad_key = ExportImportErpDatabasesUseCase(other_key_repo, other_manager)

    payload = await export_with_bad_key.export(_PASSPHRASE)

    assert payload.count == 0
    await engine.dispose()
