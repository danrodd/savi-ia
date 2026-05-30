"""Use case que resuelve el `AuthenticatedUser` a partir del access token.

Usado por la dependency `get_current_user` en cada request protegido.
- Decodifica el JWT (valida firma, exp, issuer).
- Verifica que el `purpose` sea ACCESS (no REFRESH).
- Construye el `AuthenticatedUser` desde los claims — sin pegarle a la
  BD del ERP en cada request (eso pagaría latencia y costo).

Si el admin deshabilita un usuario, este sigue con sesión activa hasta
que su access expire (~15 min). Es un trade-off conocido del JWT
stateless. Para forzar logout inmediato existe el TODO de
`revoke_all_for_user` + chequeo contra una blacklist mínima.
"""
from __future__ import annotations

from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.exceptions import InvalidTokenError
from app.modules.auth.domain.interfaces import TokenService
from app.modules.auth.domain.value_objects import TokenPurpose


class ResolveUserFromAccessTokenUseCase:
    def __init__(self, token_service: TokenService) -> None:
        self._tokens = token_service

    def execute(self, access_token: str) -> AuthenticatedUser:
        claims = self._tokens.decode(access_token)
        if claims.purpose != TokenPurpose.ACCESS:
            raise InvalidTokenError("No es un access token")
        try:
            user_id = int(claims.sub)
        except ValueError as e:
            raise InvalidTokenError("Subject inválido") from e
        return AuthenticatedUser(
            id=user_id,
            login=claims.login,
            full_name=claims.full_name,
            is_admin=claims.is_admin,
            is_active=True,
        )
