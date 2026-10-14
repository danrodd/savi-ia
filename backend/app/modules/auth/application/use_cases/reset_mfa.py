"""Restablece el segundo factor de un usuario: lo borra y cierra sus sesiones.

Lo usa un administrador (pantalla de Seguridad) o el operador del servidor por línea de
comandos cuando no queda ningún administrador que pueda entrar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.modules.auth.application.use_cases.login import split_qualified_login
from app.modules.auth.domain.interfaces import RefreshTokenRepository, TotpRepository


class DatabaseLookup(Protocol):
    """Resuelve el código de cliente (`NORTE`) a la base del ERP. `None` = la base por defecto."""

    async def database_id_for(self, code: str | None) -> UUID | None: ...


class ResetMfaUseCase:
    def __init__(
        self,
        totp_repository: TotpRepository,
        refresh_tokens: RefreshTokenRepository,
        databases: DatabaseLookup,
    ) -> None:
        self._totp = totp_repository
        self._refresh = refresh_tokens
        self._databases = databases

    async def execute(self, qualified_login: str) -> bool:
        """`True` si el usuario tenía segundo factor y se borró."""
        login, code = split_qualified_login(qualified_login)
        database_id = await self._databases.database_id_for(code)
        if database_id is None:
            return False
        user_id = await self._totp.delete_by_login(
            erp_database_id=database_id, user_login=login.strip().upper()
        )
        if user_id is None:
            return False
        # Sesiones abiertas: que vuelva a pasar por el desafío con el factor nuevo.
        await self._refresh.revoke_all_for_user(
            user_id, erp_database_id=database_id, when=datetime.now(UTC)
        )
        return True
