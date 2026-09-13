"""Impl `UserRepository` contra `Seguridad.Usuario` del ERP.

Lee del pool readonly del ERP. NUNCA escribe. La búsqueda es por
`codigo` (campo de login del ERP); el match es case-insensitive porque
el ERP guarda el código en mayúsculas pero los usuarios escriben mixed.

SOLO se exponen los campos mínimos: idUsuario, codigo, nombre, estado,
administrador. NO se leen ni se devuelven columnas sensibles (clavePermiso,
tokens internos, etc.) — el `select` es explícito.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.interfaces import UserRepository
from app.modules.auth.domain.interfaces.user_repository import UserWithHash

_SELECT_USER_SQL = """
SELECT
    "idUsuario",
    "codigo",
    "nombre",
    "clave",
    "administrador",
    "estado"
FROM "Seguridad"."Usuario"
WHERE UPPER("codigo") = UPPER(:login)
LIMIT 1
"""


class ErpUserRepository(UserRepository):
    def __init__(
        self, erp_engine: AsyncEngine, *, erp_database_id: UUID | None = None
    ) -> None:
        self._engine = erp_engine
        # Califica la identidad: el `idUsuario` solo no es único entre
        # bases de clientes. Sin esto, el usuario 5 del cliente A y el 5
        # del cliente B serían la misma persona para SAVI.
        self._erp_database_id = erp_database_id

    async def find_by_login(self, login: str) -> UserWithHash | None:
        async with self._engine.connect() as conn:
            result = await conn.execute(text(_SELECT_USER_SQL), {"login": login})
            row = result.mappings().first()
        if row is None:
            return None
        return UserWithHash(
            user=AuthenticatedUser(
                id=int(row["idUsuario"]),
                erp_database_id=self._erp_database_id,
                login=str(row["codigo"]),
                full_name=str(row["nombre"]),
                is_admin=bool(row["administrador"]),
                is_active=bool(row["estado"]),
            ),
            password_hash=str(row["clave"]),
        )
