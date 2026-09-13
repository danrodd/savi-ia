"""Tests de la resolución de permisos por base (D3) y del selector.

Lo que se protege — el corazón de D3:

- Los permisos se resuelven en la base que se consulta, no en la de
  identidad. Un admin en la base A NO obtiene módulos en la base B.
- El usuario se busca por `codigo`, no por `idUsuario` (que difiere entre
  bases).
- Una base donde el usuario no existe o está inactivo no da acceso, y no
  aparece en el selector.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.auth.application.use_cases import ResolveModulesForDatabaseUseCase
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.interfaces import (
    PermissionRepository,
    PermissionRepositoryFactory,
    SeoPlanRepository,
    SeoPlanRepositoryFactory,
    UserRepository,
    UserRepositoryFactory,
)
from app.modules.auth.domain.interfaces.user_repository import UserWithHash
from app.modules.erp_databases.application.dtos import AvailableDatabaseDTO
from app.modules.erp_databases.application.use_cases import (
    ListAvailableDatabasesUseCase,
)
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository

_DB_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_DB_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class _FakeUserRepo(UserRepository):
    """Usuario del ERP con distinto is_admin según la base."""

    def __init__(self, *, user_id: int, is_admin: bool, is_active: bool = True) -> None:
        self._user_id = user_id
        self._is_admin = is_admin
        self._is_active = is_active

    async def find_by_login(self, login: str) -> UserWithHash | None:
        return UserWithHash(
            user=AuthenticatedUser(
                id=self._user_id,
                login=login,
                full_name="Test",
                is_admin=self._is_admin,
                is_active=self._is_active,
            ),
            password_hash="x",
        )


class _AbsentUserRepo(UserRepository):
    async def find_by_login(self, login: str) -> UserWithHash | None:  # noqa: ARG002
        return None


class _FakeUserFactory(UserRepositoryFactory):
    def __init__(self, by_db: dict[UUID, UserRepository]) -> None:
        self._by_db = by_db

    async def for_code(self, code: str | None) -> UserRepository | None:  # noqa: ARG002
        return None

    async def for_database_id(self, database_id: UUID) -> UserRepository | None:
        return self._by_db.get(database_id)


class _FakePermRepo(PermissionRepository):
    def __init__(self, modules: set[str]) -> None:
        self._modules = modules

    async def get_modules_with_active_form(self, user_id: int) -> set[str]:  # noqa: ARG002
        return self._modules


class _FakePermFactory(PermissionRepositoryFactory):
    def __init__(self, by_db: dict[UUID, set[str]]) -> None:
        self._by_db = by_db

    async def for_database_id(self, database_id: UUID) -> PermissionRepository:
        return _FakePermRepo(self._by_db.get(database_id, set()))


class _FakePlanRepo(SeoPlanRepository):
    async def get_active_plan(self) -> dict[str, bool]:
        return {}


class _FakePlanFactory(SeoPlanRepositoryFactory):
    async def for_database_id(self, database_id: UUID) -> SeoPlanRepository:  # noqa: ARG002
        return _FakePlanRepo()


def _resolver(
    users: dict[UUID, UserRepository],
    perms: dict[UUID, set[str]],
) -> ResolveModulesForDatabaseUseCase:
    return ResolveModulesForDatabaseUseCase(
        _FakeUserFactory(users),
        _FakePermFactory(perms),
        _FakePlanFactory(),
    )


# ── D3: sin herencia de permisos entre bases ─────────────────────────


async def test_admin_in_one_base_is_not_admin_in_another() -> None:
    """El escenario de escalada: admin en A, usuario común en B.

    Si los permisos se heredaran de la base de identidad, un admin
    tendría acceso total a los datos de todos los clientes."""
    resolver = _resolver(
        users={
            _DB_A: _FakeUserRepo(user_id=5, is_admin=True),
            _DB_B: _FakeUserRepo(user_id=99, is_admin=False),
        },
        perms={_DB_B: set()},  # sin permisos individuales en B
    )

    access_a = await resolver.execute("JPEREZ", _DB_A)
    access_b = await resolver.execute("JPEREZ", _DB_B)

    assert access_a.is_admin_in_database is True
    assert access_b.is_admin_in_database is False
    # En B, el mismo login tiene la identidad de B (idUsuario 99), no la
    # de A (idUsuario 5).
    assert access_b.user_id_in_database == 99


async def test_no_access_when_user_absent_in_that_base() -> None:
    resolver = _resolver(users={_DB_A: _AbsentUserRepo()}, perms={})

    access = await resolver.execute("JPEREZ", _DB_A)

    assert access.has_access is False
    assert access.modules == frozenset()
    assert access.user_id_in_database is None


async def test_no_access_when_user_inactive_in_that_base() -> None:
    resolver = _resolver(
        users={_DB_A: _FakeUserRepo(user_id=5, is_admin=False, is_active=False)},
        perms={},
    )

    access = await resolver.execute("JPEREZ", _DB_A)

    assert access.has_access is False


async def test_no_access_when_database_not_usable() -> None:
    """La base no existe o está inactiva: la factory devuelve None."""
    resolver = _resolver(users={}, perms={})

    access = await resolver.execute("JPEREZ", uuid4())

    assert access.has_access is False


# ── Selector: solo bases con acceso ──────────────────────────────────


class _FakeDatabaseRepo(ErpDatabaseRepository):
    def __init__(self, databases: list[ErpDatabase]) -> None:
        self._databases = databases

    async def list_all(self, *, include_inactive: bool = False) -> list[ErpDatabase]:  # noqa: ARG002
        return self._databases

    async def get_by_id(self, database_id: UUID) -> ErpDatabase | None:
        return next((d for d in self._databases if d.id == database_id), None)

    async def get_by_code(self, code: str) -> ErpDatabase | None:  # noqa: ARG002
        return None

    async def get_default(self) -> ErpDatabase | None:
        return None

    async def count(self) -> int:
        return len(self._databases)

    async def save(self, database: ErpDatabase) -> None: ...


def _db(database_id: UUID, code: str) -> ErpDatabase:
    return ErpDatabase(
        id=database_id,
        code=code,
        name=f"Cliente {code}",
        host="h",
        port=5432,
        database=f"erp_{code}",
        username="u",
        password="p",
    )


async def test_available_lists_only_databases_with_access() -> None:
    databases = [_db(_DB_A, "NORTE"), _db(_DB_B, "SUR")]
    resolver = _resolver(
        users={
            _DB_A: _FakeUserRepo(user_id=5, is_admin=False),
            _DB_B: _AbsentUserRepo(),  # el usuario no existe en SUR
        },
        perms={_DB_A: {"VENTA"}},
    )
    use_case = ListAvailableDatabasesUseCase(
        _FakeDatabaseRepo(databases), resolver
    )

    available = await use_case.execute("JPEREZ")

    assert [a.code for a in available] == ["NORTE"]
    assert all(isinstance(a, AvailableDatabaseDTO) for a in available)
