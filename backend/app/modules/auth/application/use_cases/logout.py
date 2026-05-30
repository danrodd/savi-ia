"""Use case de logout — idempotente.

Recibe el refresh token, decodifica para sacar el `jti` y lo marca como
revocado. El access token NO se revoca (es de vida corta — el cliente
lo descarta). Idempotente: si el refresh ya estaba revocado o no
existía, igual devolvemos éxito (no le damos pistas al atacante).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.modules.auth.domain.exceptions import AuthError
from app.modules.auth.domain.interfaces import RefreshTokenRepository, TokenService
from app.modules.auth.domain.value_objects import TokenPurpose

log = logging.getLogger(__name__)


class LogoutUseCase:
    def __init__(
        self,
        refresh_token_repository: RefreshTokenRepository,
        token_service: TokenService,
    ) -> None:
        self._refresh_tokens = refresh_token_repository
        self._tokens = token_service

    async def execute(self, refresh_token: str) -> None:
        try:
            claims = self._tokens.decode(refresh_token)
        except AuthError:
            # Token inválido, expirado o malformado: igual logout es
            # idempotente. Logueamos para detección de patrones, pero
            # no fallamos.
            log.info("logout_invalid_refresh_ignored")
            return
        if claims.purpose != TokenPurpose.REFRESH or claims.jti is None:
            log.info("logout_non_refresh_token_ignored")
            return
        await self._refresh_tokens.revoke(claims.jti, when=datetime.now(UTC))
