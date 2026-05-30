from abc import ABC, abstractmethod

from app.modules.auth.domain.entities import AuthenticatedUser


class UserRepository(ABC):
    """Puerto al origen de identidades.

    Hoy implementado contra `Seguridad.Usuario` del ERP del cliente, en
    el pool readonly. NO escribe — solo lee credenciales y metadata
    mínima del usuario.
    """

    @abstractmethod
    async def find_by_login(self, login: str) -> "UserWithHash | None":
        """Busca por el `codigo` del usuario. Devuelve el user con su hash
        de password para que el use case pueda verificar; nunca expone
        el hash fuera del módulo."""


# Carga adicional: tupla con el hash, pensada para no escapar del módulo.
# Lo declaramos como dataclass dentro del archivo de puerto para que las
# implementaciones lo importen sin acoplar a infrastructure.
from dataclasses import dataclass  # noqa: E402


@dataclass(frozen=True, slots=True)
class UserWithHash:
    user: AuthenticatedUser
    password_hash: str
