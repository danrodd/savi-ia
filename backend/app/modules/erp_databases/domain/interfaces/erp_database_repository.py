"""Puerto de persistencia de las conexiones registradas al ERP.

Todos los `get_*`/`list_*` excluyen las eliminadas salvo que se pida lo
contrario: la baja es lógica porque `conversations.erp_database_id` es
una FK y el historial tiene que seguir siendo legible.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.erp_databases.domain.entities import ErpDatabase


class ErpDatabaseRepository(ABC):
    @abstractmethod
    async def get_by_id(self, database_id: UUID) -> ErpDatabase | None:
        """Devuelve la base por id, incluidas las desactivadas.

        Incluye las desactivadas a propósito: una conversación vieja
        puede apuntar a una base que ya no se usa, y hay que poder
        mostrar su nombre en el historial.
        """

    @abstractmethod
    async def get_by_code(self, code: str) -> ErpDatabase | None:
        """Devuelve la base por su código de cliente. Es la búsqueda del
        login calificado (`JPEREZ@NORTE`)."""

    @abstractmethod
    async def get_default(self) -> ErpDatabase | None:
        """Devuelve la base marcada como default, o `None` si no hay
        ninguna registrada todavía."""

    @abstractmethod
    async def list_all(self, *, include_inactive: bool = False) -> list[ErpDatabase]:
        """Lista las bases no eliminadas, ordenadas por nombre."""

    @abstractmethod
    async def count(self) -> int:
        """Total de filas, **incluidas las eliminadas**.

        Lo usa el seed de arranque para decidir si sembrar. Cuenta las
        eliminadas para no resucitar una base que el administrador dio de
        baja a propósito.
        """

    @abstractmethod
    async def save(self, database: ErpDatabase) -> None:
        """Inserta o actualiza. La contraseña se cifra acá adentro."""
