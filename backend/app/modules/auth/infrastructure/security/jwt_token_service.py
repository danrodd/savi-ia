"""Implementación del `TokenService` con PyJWT.

Algoritmo HS256 con shared secret — simple y suficiente mientras SAVI
sea un solo servicio. Cuando aparezca multi-servicio o algo que necesite
verificación distribuida sin compartir secret, se cambia a RS256 con
un KMS — esa migración no toca dominio ni use cases.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
)
from jwt.exceptions import (
    InvalidTokenError as JwtInvalidTokenError,
)

from app.infrastructure.config import Settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.exceptions import InvalidTokenError
from app.modules.auth.domain.interfaces import TokenService
from app.modules.auth.domain.value_objects import TokenClaims, TokenPurpose

# Separador del subject calificado: `"<erp_database_id>:<idUsuario>"`.
# El UUID no contiene `:` y el id es un entero, así que un `split` por el
# primero es inequívoco.
_SUB_SEPARATOR = ":"


def _qualified_subject(user: AuthenticatedUser) -> str:
    if user.erp_database_id is None:
        # Un usuario sin base es un bug de construcción, no una entrada
        # del cliente: fallar acá es preferible a emitir un token que
        # después nadie puede atribuir a un cliente.
        raise InvalidTokenError(
            "No se puede emitir un token sin la base del ERP del usuario."
        )
    return f"{user.erp_database_id}{_SUB_SEPARATOR}{user.id}"


class JwtTokenService(TokenService):
    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret
        self._algorithm = settings.jwt_algorithm
        self._issuer = settings.jwt_issuer
        self._access_ttl = timedelta(minutes=settings.access_token_ttl_minutes)
        self._refresh_lifetime = timedelta(days=settings.refresh_token_ttl_days)

    def issue_access_token(self, user: AuthenticatedUser) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": _qualified_subject(user),
            "erp_db": str(user.erp_database_id),
            "login": user.login,
            "full_name": user.full_name,
            "is_admin": user.is_admin,
            "purpose": TokenPurpose.ACCESS.value,
            "iss": self._issuer,
            "iat": now,
            "exp": now + self._access_ttl,
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def issue_refresh_token(
        self, user: AuthenticatedUser, *, jti: UUID, expires_at: datetime
    ) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": _qualified_subject(user),
            "erp_db": str(user.erp_database_id),
            "login": user.login,
            "full_name": user.full_name,
            "is_admin": user.is_admin,
            "purpose": TokenPurpose.REFRESH.value,
            "jti": str(jti),
            "iss": self._issuer,
            "iat": now,
            "exp": expires_at,
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "purpose"]},
            )
        except ExpiredSignatureError as e:
            raise InvalidTokenError("Token expirado") from e
        except (
            InvalidSignatureError,
            InvalidIssuerError,
            InvalidAudienceError,
            JwtInvalidTokenError,
        ) as e:
            raise InvalidTokenError(f"Token inválido: {e}") from e

        try:
            purpose = TokenPurpose(payload["purpose"])
        except ValueError as e:
            raise InvalidTokenError("Purpose desconocido") from e

        jti_raw = payload.get("jti")
        jti = UUID(jti_raw) if jti_raw else None

        sub = str(payload["sub"])
        erp_database_id, user_id = _parse_subject(sub)

        return TokenClaims(
            sub=sub,
            erp_database_id=erp_database_id,
            user_id=user_id,
            login=str(payload.get("login", "")),
            full_name=str(payload.get("full_name", "")),
            is_admin=bool(payload.get("is_admin", False)),
            purpose=purpose,
            jti=jti,
        )

    def access_token_ttl_seconds(self) -> int:
        return int(self._access_ttl.total_seconds())

    def refresh_token_lifetime_seconds(self) -> int:
        return int(self._refresh_lifetime.total_seconds())


def _parse_subject(sub: str) -> tuple[UUID, int]:
    """Parte `"<erp_database_id>:<idUsuario>"` y valida las dos mitades.

    **Un `sub` sin la base se rechaza**, aunque sea un entero válido. Son
    los tokens emitidos antes del multi-BD: adivinar que pertenecían a la
    base default es exactamente el cruce de identidades que este cambio
    viene a evitar. El efecto para el usuario es volver a iniciar sesión
    una vez, igual que ante un cambio de `JWT_SECRET`.
    """
    raw_database_id, separator, raw_user_id = sub.partition(_SUB_SEPARATOR)
    if not separator:
        raise InvalidTokenError(
            "Token emitido antes del soporte multi-base. Iniciá sesión de nuevo."
        )
    try:
        return UUID(raw_database_id), int(raw_user_id)
    except ValueError as e:
        raise InvalidTokenError("Subject inválido") from e
