"""Use case de refresh.

Rotación: emitimos un access NUEVO y un refresh NUEVO, y revocamos el
viejo. Esto reduce la ventana de uso de un refresh robado y deja
trazabilidad por sesión.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.modules.auth.domain.entities import AuthenticatedUser, RefreshTokenRecord
from app.modules.auth.domain.exceptions import (
    InvalidTokenError,
    RefreshTokenRevokedError,
    UserDisabledError,
)
from app.modules.auth.domain.interfaces import (
    RefreshTokenRepository,
    TokenService,
    UserRepository,
)
from app.modules.auth.domain.value_objects import TokenPair, TokenPurpose


class RefreshTokensUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
        token_service: TokenService,
    ) -> None:
        self._users = user_repository
        self._refresh_tokens = refresh_token_repository
        self._tokens = token_service

    async def execute(
        self, refresh_token: str
    ) -> tuple[TokenPair, AuthenticatedUser]:
        claims = self._tokens.decode(refresh_token)
        if claims.purpose != TokenPurpose.REFRESH or claims.jti is None:
            raise InvalidTokenError("No es un refresh token")

        record = await self._refresh_tokens.get_by_jti(claims.jti)
        if record is None:
            raise InvalidTokenError("Token desconocido")
        if record.is_revoked:
            raise RefreshTokenRevokedError
        if record.expires_at <= datetime.now(UTC):
            raise InvalidTokenError("Token expirado")

        # Re-leemos el usuario del origen — un admin puede haber
        # deshabilitado la cuenta mientras la sesión seguía abierta.
        fresh = await self._users.find_by_login(claims.login)
        if fresh is None:
            raise InvalidTokenError("Usuario no encontrado")
        if not fresh.user.is_active:
            raise UserDisabledError

        now = datetime.now(UTC)
        await self._refresh_tokens.revoke(claims.jti, when=now)

        new_jti = uuid4()
        new_expires = now + timedelta(
            seconds=self._tokens.refresh_token_lifetime_seconds()
        )
        new_refresh = self._tokens.issue_refresh_token(
            fresh.user, jti=new_jti, expires_at=new_expires
        )
        await self._refresh_tokens.save(
            RefreshTokenRecord(
                jti=new_jti,
                user_id=fresh.user.id,
                user_login=fresh.user.login,
                expires_at=new_expires,
                created_at=now,
            )
        )

        new_access = self._tokens.issue_access_token(fresh.user)
        pair = TokenPair(
            access_token=new_access,
            refresh_token=new_refresh,
            access_token_expires_in=self._tokens.access_token_ttl_seconds(),
        )
        return pair, fresh.user
