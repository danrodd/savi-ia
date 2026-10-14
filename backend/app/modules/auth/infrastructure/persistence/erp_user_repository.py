"""Impl `UserRepository` contra `Seguridad.Usuario` del ERP.

Lee del pool readonly del ERP. NUNCA escribe. La búsqueda es por
`codigo` (campo de login del ERP); el match es case-insensitive porque
el ERP guarda el código en mayúsculas pero los usuarios escriben mixed.

SOLO se exponen los campos mínimos: idUsuario, codigo, nombre, estado,
administrador. NO se leen ni se devuelven columnas sensibles (clavePermiso,
tokens internos, etc.) — el `select` es explícito.
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.exceptions import DatabaseUnreachableError
from app.modules.auth.domain.interfaces import UserRepository
from app.modules.auth.domain.interfaces.user_repository import UserWithHash

logger = logging.getLogger(__name__)

# Tope de espera de la consulta de login. El connect de asyncpg espera 60 s
# por defecto: una base caída dejaría la pantalla de login colgada un minuto.
_QUERY_TIMEOUT_SECONDS = 10.0

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
        try:
            row = await asyncio.wait_for(self._fetch_row(login), _QUERY_TIMEOUT_SECONDS)
        except (SQLAlchemyError, OSError) as exc:
            # `TimeoutError` es un `OSError`. Sin el `from`, el log no
            # arrastra el DSN: solo el tipo de falla.
            logger.warning(
                "No se pudo consultar el ERP %s en el login: %s",
                self._erp_database_id,
                type(exc).__name__,
            )
            raise DatabaseUnreachableError from None
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

    async def _fetch_row(self, login: str) -> RowMapping | None:
        async with self._engine.connect() as conn:
            result = await conn.execute(text(_SELECT_USER_SQL), {"login": login})
            return result.mappings().first()
