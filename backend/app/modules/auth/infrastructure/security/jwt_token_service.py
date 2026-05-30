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
            "sub": str(user.id),
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
            "sub": str(user.id),
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

        return TokenClaims(
            sub=str(payload["sub"]),
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
