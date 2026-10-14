from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.modules.auth.domain.entities import UserTotp


class TotpRepository(ABC):
    """Persistencia del segundo factor. El secreto viaja en claro por este puerto y se
    guarda cifrado: el cifrado es un detalle de la implementación."""

    @abstractmethod
    async def get(self, *, erp_database_id: UUID, user_id: int) -> UserTotp | None: ...

    @abstractmethod
    async def save_pending(
        self,
        *,
        erp_database_id: UUID,
        user_id: int,
        user_login: str,
        secret: str,
        when: datetime,
    ) -> None:
        """Guarda un secreto sin activar. Reemplaza uno pendiente anterior. Nunca pisa uno
        activo: eso solo lo hace un restablecimiento."""

    @abstractmethod
    async def enable(
        self, *, erp_database_id: UUID, user_id: int, last_step: int, when: datetime
    ) -> bool:
        """Activa el secreto pendiente. `False` si no había uno pendiente."""

    @abstractmethod
    async def advance_step(self, *, erp_database_id: UUID, user_id: int, step: int) -> bool:
        """Registra `step` como usado, de forma atómica. `False` si ya estaba usado (o uno
        posterior): dos pedidos simultáneos con el mismo código no pasan los dos."""

    @abstractmethod
    async def delete_by_login(self, *, erp_database_id: UUID, user_login: str) -> int | None:
        """Elimina el segundo factor del usuario. Devuelve su `user_id`, o `None` si no tenía."""
