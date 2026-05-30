"""Use case de login.

Flujo:
1. Buscar el usuario por `login` en el origen de identidades (ERP).
2. Si no existe o está deshabilitado → InvalidCredentialsError (no
   distinguimos "user no existe" de "password mal" para no filtrar
   info al atacante).
3. Verificar password contra el hash (MD5 hoy).
4. Emitir access + refresh tokens.
5. Persistir el `jti` del refresh para soportar revocación en logout.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.modules.auth.domain.entities import AuthenticatedUser, RefreshTokenRecord
from app.modules.auth.domain.exceptions import (
    InvalidCredentialsError,
    UserDisabledError,
)
from app.modules.auth.domain.interfaces import (
    PasswordHasher,
    RefreshTokenRepository,
    TokenService,
    UserRepository,
)
from app.modules.auth.domain.value_objects import TokenPair


class LoginUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
        password_hasher: PasswordHasher,
        token_service: TokenService,
    ) -> None:
        self._users = user_repository
        self._refresh_tokens = refresh_token_repository
        self._hasher = password_hasher
        self._tokens = token_service

    async def execute(
        self, login: str, password: str
    ) -> tuple[TokenPair, AuthenticatedUser]:
        # Normalizamos a mayúsculas porque el `codigo` del ERP está así.
        found = await self._users.find_by_login(login.strip().upper())
        if found is None:
            raise InvalidCredentialsError
        if not self._hasher.verify(password, found.password_hash):
            raise InvalidCredentialsError
        if not found.user.is_active:
            # Distinguimos "deshabilitado" para que el frontend pueda
            # mostrar "tu cuenta está suspendida" en lugar de "credencial
            # inválida" — y el log también lo registra distinto.
            raise UserDisabledError

        access = self._tokens.issue_access_token(found.user)

        jti = uuid4()
        now = datetime.now(UTC)
        expires_at = now + timedelta(
            seconds=self._tokens.refresh_token_lifetime_seconds()
        )
        refresh = self._tokens.issue_refresh_token(
            found.user, jti=jti, expires_at=expires_at
        )
        await self._refresh_tokens.save(
            RefreshTokenRecord(
                jti=jti,
                user_id=found.user.id,
                user_login=found.user.login,
                expires_at=expires_at,
                created_at=now,
            )
        )

        pair = TokenPair(
            access_token=access,
            refresh_token=refresh,
            access_token_expires_in=self._tokens.access_token_ttl_seconds(),
        )
        return pair, found.user
