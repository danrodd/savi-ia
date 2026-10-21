"""Segundo factor (TOTP): desafío en el login, configuración y verificación.

Flujo (la contraseña ya se verificó contra el ERP):

    login ──► ¿le toca MFA?  no ──► sesión normal
                  │ sí
                  ├─ TOTP activo ────► `mfa_required`        + token MFA        (5 min)
                  └─ sin TOTP ───────► `mfa_setup_required`  + token MFA_SETUP  (10 min)

Los tokens de este módulo **no abren sesión**: solo sirven en `/auth/mfa/*`. La sesión real
(access + refresh) se emite recién cuando el código es correcto.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.domain.exceptions import (
    InvalidMfaCodeError,
    InvalidTokenError,
    MfaUnavailableError,
)
from app.modules.auth.domain.interfaces import TokenService, TotpRepository
from app.modules.auth.domain.value_objects import TokenPurpose
from app.shared.security import totp

MFA_TOKEN_TTL_SECONDS = 5 * 60
MFA_SETUP_TOKEN_TTL_SECONDS = 10 * 60

_UNAVAILABLE = (
    "Su verificación en dos pasos no se puede usar. Pídale a un administrador que la restablezca."
)


@dataclass(frozen=True, slots=True)
class MfaChallenge:
    token: str
    setup_required: bool
    expires_in: int


@dataclass(frozen=True, slots=True)
class MfaSetup:
    secret: str
    otpauth_uri: str


class MfaChallengeRequired(Exception):  # noqa: N818 — control de flujo del login, no un error
    """El login verificó la contraseña pero falta el segundo factor.

    No es un fallo: la ruta la atrapa y responde 200 con el desafío. Es una excepción para no
    cambiar la firma de `LoginUseCase.execute`, que ya consumen otros llamadores.
    """

    def __init__(self, challenge: MfaChallenge) -> None:
        super().__init__("Falta el segundo factor")
        self.challenge = challenge


class MfaGate(Protocol):
    async def challenge_for(self, user: AuthenticatedUser) -> MfaChallenge | None: ...


class MfaService:
    def __init__(
        self,
        *,
        totp_repository: TotpRepository,
        token_service: TokenService,
        is_required: Callable[[AuthenticatedUser], bool],
        issuer: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._totp = totp_repository
        self._tokens = token_service
        self._is_required = is_required
        self._issuer = issuer
        self._now = now

    # ── login ──────────────────────────────────────────────────────────
    async def challenge_for(self, user: AuthenticatedUser) -> MfaChallenge | None:
        if not self._is_required(user):
            return None
        record = await self._totp.get(erp_database_id=_database(user), user_id=user.id)
        if record is not None and record.unreadable:
            # No se degrada a "configurar de nuevo": quien tenga la contraseña se enrolaría su
            # propio TOTP y se saltaría el segundo factor. Hace falta un administrador.
            raise MfaUnavailableError(_UNAVAILABLE)
        if record is not None and record.enabled:
            return MfaChallenge(
                token=self._tokens.issue_mfa_token(
                    user, purpose=TokenPurpose.MFA, ttl_seconds=MFA_TOKEN_TTL_SECONDS
                ),
                setup_required=False,
                expires_in=MFA_TOKEN_TTL_SECONDS,
            )
        return MfaChallenge(
            token=self._tokens.issue_mfa_token(
                user, purpose=TokenPurpose.MFA_SETUP, ttl_seconds=MFA_SETUP_TOKEN_TTL_SECONDS
            ),
            setup_required=True,
            expires_in=MFA_SETUP_TOKEN_TTL_SECONDS,
        )

    # ── configuración ──────────────────────────────────────────────────
    async def begin_setup(self, token: str, *, account_label: str) -> MfaSetup:
        user = self._user_from(token, TokenPurpose.MFA_SETUP)
        record = await self._totp.get(erp_database_id=_database(user), user_id=user.id)
        if record is not None and (record.enabled or record.unreadable):
            raise MfaUnavailableError(
                "Ya tiene la verificación en dos pasos configurada. "
                "Si perdió el acceso, pídale a un administrador que la restablezca."
            )
        secret = totp.generate_secret()
        await self._totp.save_pending(
            erp_database_id=_database(user),
            user_id=user.id,
            user_login=user.login,
            secret=secret,
            when=self._now(),
        )
        return MfaSetup(
            secret=secret,
            otpauth_uri=totp.otpauth_uri(secret, account_label, self._issuer),
        )

    async def confirm_setup(self, token: str, code: str) -> AuthenticatedUser:
        user = self._user_from(token, TokenPurpose.MFA_SETUP)
        record = await self._totp.get(erp_database_id=_database(user), user_id=user.id)
        if record is None or record.enabled or record.unreadable or record.secret is None:
            raise InvalidMfaCodeError
        step = totp.verify(record.secret, code, self._now(), last_step=0)
        if step is None:
            raise InvalidMfaCodeError
        enabled = await self._totp.enable(
            erp_database_id=_database(user), user_id=user.id, last_step=step, when=self._now()
        )
        if not enabled:
            raise InvalidMfaCodeError
        return user

    # ── verificación ───────────────────────────────────────────────────
    async def verify(self, token: str, code: str) -> AuthenticatedUser:
        user = self._user_from(token, TokenPurpose.MFA)
        record = await self._totp.get(erp_database_id=_database(user), user_id=user.id)
        if record is None or not record.enabled:
            # Lo restablecieron entre el login y este paso: que vuelva a entrar.
            raise InvalidTokenError("La verificación venció. Inicie sesión de nuevo.")
        if record.unreadable or record.secret is None:
            raise MfaUnavailableError(_UNAVAILABLE)
        step = totp.verify(record.secret, code, self._now(), record.last_step)
        if step is None:
            raise InvalidMfaCodeError
        # Atómico: dos pedidos simultáneos con el mismo código no pasan los dos.
        if not await self._totp.advance_step(
            erp_database_id=_database(user), user_id=user.id, step=step
        ):
            raise InvalidMfaCodeError
        return user

    # ── interno ────────────────────────────────────────────────────────
    def _user_from(self, token: str, expected: TokenPurpose) -> AuthenticatedUser:
        claims = self._tokens.decode(token)
        if claims.purpose != expected:
            raise InvalidTokenError("Este token no sirve para este paso.")
        return AuthenticatedUser(
            id=claims.user_id,
            login=claims.login,
            full_name=claims.full_name,
            is_admin=claims.is_admin,
            is_active=True,
            erp_database_id=claims.erp_database_id,
        )


def _database(user: AuthenticatedUser):  # type: ignore[no-untyped-def]
    if user.erp_database_id is None:
        raise InvalidTokenError("El usuario no tiene base de ERP asociada.")
    return user.erp_database_id
