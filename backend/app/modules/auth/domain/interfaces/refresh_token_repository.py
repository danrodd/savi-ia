from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.modules.auth.domain.entities import RefreshTokenRecord


class RefreshTokenRepository(ABC):
    """Persistencia de refresh tokens emitidos.

    Habilita revocación real en `logout` (sin necesidad de una blacklist
    inmensa: los tokens revocados se marcan y se purgan periódicamente).
    """

    @abstractmethod
    async def save(self, record: RefreshTokenRecord) -> None: ...

    @abstractmethod
    async def get_by_jti(self, jti: UUID) -> RefreshTokenRecord | None: ...

    @abstractmethod
    async def revoke(self, jti: UUID, *, when: datetime) -> bool:
        """Marca el token como revocado. Devuelve True si existía y no
        estaba ya revocado, False en otro caso (idempotente)."""

    @abstractmethod
    async def revoke_all_for_user(
        self, user_id: int, *, when: datetime
    ) -> None:
        """Revoca todos los refresh tokens vigentes de un usuario.

        Útil para logout-everywhere o cambio de contraseña. No se usa
        en el flujo básico actual pero está preparado.
        """
