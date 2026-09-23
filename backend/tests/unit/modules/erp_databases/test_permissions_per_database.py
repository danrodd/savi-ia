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
    use_case = ListAvailableDatabasesUseCase(_FakeDatabaseRepo(databases), resolver)

    available = await use_case.execute("JPEREZ")

    assert [a.code for a in available] == ["NORTE"]
    assert all(isinstance(a, AvailableDatabaseDTO) for a in available)


# ── Administrador de la instalación (soporte) ────────────────────────
#
# Entra a cualquier base activa como administrador, aunque su código no
# exista ahí: si no, soporte tenía que cerrar sesión y volver a entrar con
# `CODIGO@BASE` para cada cliente.

_SOPORTE = AuthenticatedUser(
    id=1, erp_database_id=_DB_A, login="ADMIN", full_name="Soporte", is_admin=True, is_active=True
)
# Mismo código, OTRA persona: el administrador del cliente B.
_ADMIN_DE_B = AuthenticatedUser(
    id=1, erp_database_id=_DB_B, login="ADMIN", full_name="Admin B", is_admin=True, is_active=True
)


async def _solo_soporte(user: AuthenticatedUser) -> bool:
    """Política de prueba: administra la instalación quien entró por A."""
    return user.erp_database_id == _DB_A and user.is_admin


def _resolver_con_politica(users: dict[UUID, UserRepository]) -> ResolveModulesForDatabaseUseCase:
    return ResolveModulesForDatabaseUseCase(
        _FakeUserFactory(users), _FakePermFactory({}), _FakePlanFactory(), _solo_soporte
    )


async def test_platform_admin_enters_a_base_where_their_code_does_not_exist() -> None:
    resolver = _resolver_con_politica({_DB_B: _AbsentUserRepo()})

    access = await resolver.execute("ADMIN", _DB_B, identity=_SOPORTE)

    assert access.has_access is True
    assert access.is_admin_in_database is True
    # No hay identidad en esa base: no se inventa un idUsuario.
    assert access.user_id_in_database is None


async def test_company_admin_with_the_same_code_does_not_get_other_clients() -> None:
    """El admin del cliente B también se llama ADMIN: la política mira la
    identidad completa, no el código."""
    resolver = _resolver_con_politica({_DB_A: _AbsentUserRepo()})

    access = await resolver.execute("ADMIN", _DB_A, identity=_ADMIN_DE_B)

    assert access.has_access is False


async def test_platform_admin_respects_an_explicit_deactivation() -> None:
    """Si el código existe en la base y el ERP lo desactivó, gana el bloqueo."""
    resolver = _resolver_con_politica(
        {_DB_B: _FakeUserRepo(user_id=7, is_admin=False, is_active=False)}
    )

    access = await resolver.execute("ADMIN", _DB_B, identity=_SOPORTE)

    assert access.has_access is False


async def test_without_identity_the_exception_does_not_apply() -> None:
    """Simular qué vería un login (prueba de búsqueda) no pasa identidad:
    se resuelve solo por el código, como un usuario común."""
    resolver = _resolver_con_politica({_DB_B: _AbsentUserRepo()})

    access = await resolver.execute("ADMIN", _DB_B)

    assert access.has_access is False


async def test_platform_admin_cannot_enter_an_unusable_base() -> None:
    resolver = _resolver_con_politica({})

    access = await resolver.execute("ADMIN", uuid4(), identity=_SOPORTE)

    assert access.has_access is False


async def test_selector_lists_every_active_base_for_the_platform_admin() -> None:
    """Soporte existe en A y no en B: igual ve las dos."""
    resolver = _resolver_con_politica(
        {_DB_A: _FakeUserRepo(user_id=1, is_admin=True), _DB_B: _AbsentUserRepo()}
    )
    bases = _FakeDatabaseRepo([_db(_DB_A, "A"), _db(_DB_B, "B")])

    visibles = await ListAvailableDatabasesUseCase(bases, resolver).execute(
        "ADMIN", identity=_SOPORTE
    )

    assert {d.code for d in visibles} == {"A", "B"}


async def test_selector_keeps_company_admins_in_their_own_bases() -> None:
    """El admin de B ve solo B, aunque su código exista en A."""
    resolver = _resolver_con_politica(
        {
            _DB_A: _FakeUserRepo(user_id=1, is_admin=True),
            _DB_B: _FakeUserRepo(user_id=1, is_admin=True),
        }
    )
    bases = _FakeDatabaseRepo([_db(_DB_A, "A"), _db(_DB_B, "B")])

    visibles = await ListAvailableDatabasesUseCase(bases, resolver).execute(
        "ADMIN", identity=_ADMIN_DE_B
    )

    assert {d.code for d in visibles} == {"B"}


# ── Un usuario común no cruza a otra base ────────────────────────────
#
# "Mismo código = misma persona" no es cierto entre clientes. Medido en los
# ERP locales: `AUX2` es Karen Restrepo en frami e Ingrid Tovar en
# sur_andina. Con el cruce por código, Karen entraba a sur_andina con los
# permisos de Ingrid.

_KAREN = AuthenticatedUser(
    id=12, erp_database_id=_DB_A, login="AUX2", full_name="Karen", is_admin=False, is_active=True
)


async def test_regular_user_cannot_enter_another_base_with_the_same_code() -> None:
    resolver = _resolver_con_politica(
        {
            _DB_A: _FakeUserRepo(user_id=12, is_admin=False),
            _DB_B: _FakeUserRepo(user_id=40, is_admin=True),  # Ingrid, admin en B
        }
    )

    access = await resolver.execute("AUX2", _DB_B, identity=_KAREN)

    assert access.has_access is False
    assert access.modules == frozenset()


async def test_regular_user_keeps_access_to_their_own_base() -> None:
    resolver = _resolver_con_politica({_DB_A: _FakeUserRepo(user_id=12, is_admin=False)})

    access = await resolver.execute("AUX2", _DB_A, identity=_KAREN)

    assert access.has_access is True
    assert access.user_id_in_database == 12


async def test_selector_shows_a_regular_user_only_their_own_base() -> None:
    resolver = _resolver_con_politica(
        {
            _DB_A: _FakeUserRepo(user_id=12, is_admin=False),
            _DB_B: _FakeUserRepo(user_id=40, is_admin=True),
        }
    )
    bases = _FakeDatabaseRepo([_db(_DB_A, "A"), _db(_DB_B, "B")])

    visibles = await ListAvailableDatabasesUseCase(bases, resolver).execute("AUX2", identity=_KAREN)

    assert {d.code for d in visibles} == {"A"}


async def test_platform_admin_uses_their_real_permissions_where_their_code_exists() -> None:
    """Si soporte tiene usuario en la base destino, entra con ese usuario
    (su idUsuario y permisos de ahí), no con un administrador genérico."""
    resolver = _resolver_con_politica({_DB_B: _FakeUserRepo(user_id=7, is_admin=False)})

    access = await resolver.execute("ADMIN", _DB_B, identity=_SOPORTE)

    assert access.has_access is True
    assert access.user_id_in_database == 7
    assert access.is_admin_in_database is False
