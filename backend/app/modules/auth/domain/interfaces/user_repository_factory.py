"""Puerto que produce un `UserRepository` apuntado a una base concreta.

Existe porque con varias bases de clientes el repositorio de usuarios ya
no se puede inyectar resuelto: cuál usar depende del login que llega en
el request (`JPEREZ@NORTE`), y eso se sabe recién dentro del caso de uso.

El caso de uso depende de este puerto y no del registry de engines: la
capa de aplicación no sabe qué es un engine ni cómo se resuelve un
código de cliente.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.auth.domain.interfaces.user_repository import UserRepository


class UserRepositoryFactory(ABC):
    @abstractmethod
    async def for_code(self, code: str | None) -> UserRepository | None:
        """Repositorio de usuarios de la base con ese código, o de la
        default si `code` es `None`.

        Devuelve `None` —y no levanta— cuando la base no existe, está
        desactivada, fue eliminada o tiene credenciales ilegibles. El
        caso de uso lo traduce a "credenciales inválidas", que es la
        misma respuesta que da ante una contraseña mala: distinguirlos
        permitiría enumerar los clientes registrados desde el login.
        """

    @abstractmethod
    async def for_database_id(self, database_id: UUID) -> UserRepository | None:
        """Igual que `for_code`, pero por id. Lo usa el refresh, que ya
        tiene la base resuelta desde los claims del token."""
