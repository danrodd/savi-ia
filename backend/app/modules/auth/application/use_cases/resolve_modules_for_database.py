"""Resuelve los módulos de un usuario **en una base del ERP concreta** (D3).

Es la pieza que impide la escalada de privilegios entre clientes. El
`idUsuario` no sirve entre bases, así que el usuario se busca por su
`codigo` (login, estable porque el esquema es el mismo) en la base que se
va a consultar, y los permisos se leen de ESA base.

Si el `codigo` no existe en la base, o existe pero está inactivo, el
usuario **no tiene acceso** a esa base: no se hereda ni el `is_admin` ni
los módulos de la base donde se autenticó.

CRUZAR A OTRA BASE es solo para el administrador de la instalación
(soporte). Un usuario común usa únicamente la base con la que inició
sesión: "mismo código = misma persona" NO es cierto entre clientes. Medido
en los ERP locales: `AUX2` es Karen Restrepo en frami e Ingrid Tovar en
sur_andina; con el cruce por código, Karen habría entrado a sur_andina con
los permisos de Ingrid.

El administrador de la instalación entra a cualquier base activa: con sus
permisos reales si su código existe ahí, o como administrador si no existe
(así soporte no cierra sesión para atender a cada cliente). Quién lo es lo
decide una política inyectada que mira la identidad completa (código +
base de login + rol), no solo el código. Si su código existe en la base
destino y el ERP lo desactivó, se respeta el bloqueo.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from app.modules.auth.application.use_cases.resolve_user_modules import (
    ResolveUserModulesUseCase,
)
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.interfaces import (
    PermissionRepositoryFactory,
    SeoPlanRepositoryFactory,
    UserRepositoryFactory,
)
from app.modules.auth.domain.value_objects import ModuleCode


@dataclass(frozen=True, slots=True)
class DatabaseAccess:
    """Resultado de resolver el acceso de un usuario a una base.

    `has_access=False` cuando el usuario no existe o está inactivo en esa
    base. En ese caso `modules` está vacío y `user_id_in_database` es
    `None`: no hay identidad que resolver ahí.
    """

    has_access: bool
    modules: frozenset[ModuleCode]
    user_id_in_database: int | None = None
    is_admin_in_database: bool = False
    # Hash de los módulos, para que el frontend detecte cambios sin traerse
    # el bootstrap entero. Vacío cuando no hay acceso: no hay nada que versionar.
    version: str = ""


PlatformAdminPolicy = Callable[[AuthenticatedUser], Awaitable[bool]]


class ResolveModulesForDatabaseUseCase:
    def __init__(
        self,
        user_repository_factory: UserRepositoryFactory,
        permission_repo_factory: PermissionRepositoryFactory,
        seo_plan_repo_factory: SeoPlanRepositoryFactory,
        is_platform_admin: PlatformAdminPolicy | None = None,
    ) -> None:
        self._users = user_repository_factory
        self._permissions = permission_repo_factory
        self._plans = seo_plan_repo_factory
        self._is_platform_admin = is_platform_admin

    async def execute(
        self,
        login: str,
        database_id: UUID,
        *,
        identity: AuthenticatedUser | None = None,
    ) -> DatabaseAccess:
        """`identity` es el usuario autenticado; con ella se aplica la regla
        de cruce entre bases. Sin ella (p. ej. un administrador simulando qué
        vería un login en una base que eligió) se resuelve solo por el
        código."""
        crosses_database = identity is not None and identity.erp_database_id != database_id
        is_platform_admin = await self._platform_admin(identity)
        if crosses_database and not is_platform_admin:
            return DatabaseAccess(has_access=False, modules=frozenset())

        repository = await self._users.for_database_id(database_id)
        if repository is None:
            # La base no existe o no se puede usar: sin acceso, sin filtrar
            # nada. El caller decide si es 404 o 409.
            return DatabaseAccess(has_access=False, modules=frozenset())

        found = await repository.find_by_login(login.strip().upper())
        if found is None and is_platform_admin:
            # Soporte entrando a un cliente donde no tiene usuario: acceso de
            # administrador, sin identidad en esa base.
            resolution = await ResolveUserModulesUseCase(
                await self._permissions.for_database_id(database_id),
                await self._plans.for_database_id(database_id),
            ).execute(0, is_admin=True)
            return DatabaseAccess(
                has_access=True,
                modules=resolution.modules,
                user_id_in_database=None,
                is_admin_in_database=True,
                version=resolution.version,
            )
        if found is None or not found.user.is_active:
            # El codigo no existe en esta base, o está inactivo: sin acceso.
            # NO se heredan permisos de la base de identidad.
            return DatabaseAccess(has_access=False, modules=frozenset())

        # Con la identidad de ESTA base (su idUsuario, su is_admin),
        # resolvemos los módulos contra los permisos de ESTA base.
        permissions = await self._permissions.for_database_id(database_id)
        plans = await self._plans.for_database_id(database_id)
        resolver = ResolveUserModulesUseCase(permissions, plans)
        resolution = await resolver.execute(found.user.id, is_admin=found.user.is_admin)

        return DatabaseAccess(
            has_access=True,
            modules=resolution.modules,
            user_id_in_database=found.user.id,
            is_admin_in_database=found.user.is_admin,
            version=resolution.version,
        )

    async def _platform_admin(self, identity: AuthenticatedUser | None) -> bool:
        if identity is None or self._is_platform_admin is None:
            return False
        return await self._is_platform_admin(identity)
