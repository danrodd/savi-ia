"""Puerto: ¿qué bases puede consultar esta persona según SEO Group?

Solo restringe lo que el ERP ya permite. La resolución real vive en `cloud_link`.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.erp_databases.domain.exceptions import DatabaseNotAssignedError


class DatabaseAccessPolicy(ABC):
    @abstractmethod
    async def allowed_databases(
        self, *, user_id: int, identity_database_id: UUID
    ) -> frozenset[UUID] | None:
        """`None` = sin restricción (manda el ERP)."""

    async def ensure(
        self, *, user_id: int, identity_database_id: UUID, database_id: UUID
    ) -> None:
        allowed = await self.allowed_databases(
            user_id=user_id, identity_database_id=identity_database_id
        )
        if allowed is not None and database_id not in allowed:
            raise DatabaseNotAssignedError(
                "SEO Group no te asignó esta base de datos. "
                "Si la necesitás, pedíselo a soporte."
            )


class UnrestrictedDatabases(DatabaseAccessPolicy):
    """Sin vinculación a Cloud (o sin servicio): no hay nadie que restrinja."""

    async def allowed_databases(
        self, *, user_id: int, identity_database_id: UUID
    ) -> frozenset[UUID] | None:
        return None
