"""Casos de uso de autenticación del staff (§2 de la Fase 3).

Los pasos que registran intentos fallidos (login, MFA) **devuelven** un `AuthFailure` en vez
de levantar la excepción: la transacción debe confirmarse (contador, bloqueo y auditoría)
y recién después la ruta responde con el error.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from app.modules.audit.application import AuditRecorder
from app.modules.audit.domain import RequestContext
from app.modules.staff.domain import (
    InvalidSessionToken,
    InvalidStaffData,
    Role,
    SessionRepository,
    StaffEmailAlreadyExists,
    StaffRepository,
    StaffSession,
    StaffUser,
    WeakPassword,
)
from app.modules.staff.security import (
    ACCESS_TTL,
    MFA_SETUP_TTL,
    MFA_TTL,
    REFRESH_TTL,
    StaffSecurity,
    generate_temporary_password,
    generate_totp_secret,
    otpauth_uri,
    validate_password_policy,
    verify_totp,
)
from app.shared.clock import Clock

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=15)

EMAIL_MAX_LENGTH = 254


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True)
class AuthDeps:
    users: StaffRepository
    sessions: SessionRepository
    audit: AuditRecorder
    security: StaffSecurity
    clock: Clock


@dataclass(frozen=True)
class AuthFailure:
    code: str
    message: str


INVALID_CREDENTIALS = AuthFailure("invalid_credentials", "Correo o contraseña incorrectos.")
INVALID_MFA = AuthFailure("invalid_mfa_code", "El código no es válido.")


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    must_change_password: bool
    user: StaffUser


@dataclass(frozen=True)
class LoginStep:
    """Resultado del paso de contraseña: qué sigue y con qué token de un solo propósito."""

    next_step: Literal["mfa_required", "mfa_setup_required"]
    token: str
    # Solo informativo para la pantalla: la contraseña nueva se exige en la confirmación.
    must_change_password: bool = False


@dataclass(frozen=True)
class MfaSetup:
    secret: str
    otpauth_uri: str


@dataclass(frozen=True)
class Principal:
    user: StaffUser
    session: StaffSession


def _lock_state(user: StaffUser, now: datetime) -> StaffUser:
    """Suma un fallo; al llegar al tope bloquea la cuenta y reinicia el contador."""
    attempts = user.failed_attempts + 1
    if attempts >= MAX_FAILED_ATTEMPTS:
        return replace(user, failed_attempts=0, locked_until=now + LOCK_DURATION, updated_at=now)
    return replace(user, failed_attempts=attempts, updated_at=now)


async def _open_session(
    deps: AuthDeps, user: StaffUser, ctx: RequestContext, *, expires_at: datetime | None = None
) -> TokenPair:
    now = deps.clock()
    session = StaffSession(
        jti=uuid4(),
        staff_user_id=user.id,
        created_at=now,
        last_used_at=now,
        expires_at=expires_at or now + REFRESH_TTL,
        ip=ctx.ip,
        user_agent=(ctx.user_agent or "")[:256] or None,
    )
    await deps.sessions.add(session)
    access = deps.security.issue(
        "access", user.id, ACCESS_TTL, jti=str(session.jti), role=user.role.value
    )
    remaining = max(session.expires_at - now, timedelta(0))
    refresh = deps.security.issue("refresh", user.id, remaining, jti=str(session.jti))
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=int(ACCESS_TTL.total_seconds()),
        must_change_password=user.must_change_password,
        user=user,
    )


class LoginUseCase:
    def __init__(self, deps: AuthDeps) -> None:
        self._d = deps

    async def execute(
        self, email: str, password: str, ctx: RequestContext
    ) -> LoginStep | AuthFailure:
        d = self._d
        now = d.clock()
        clean = normalize_email(email)
        user = await d.users.get_by_email(clean)
        failed_ctx = replace(ctx, actor_email=clean)

        if user is None:
            await d.security.dummy_verify(password)
            await d.audit.record(failed_ctx, "auth.login_failed", after={"reason": "unknown"})
            return INVALID_CREDENTIALS

        ok = await d.security.verify_password(user.password_hash, password)
        locked = user.locked_until is not None and user.locked_until > now
        if locked or not user.is_active:
            # Mismo error y mismo costo que una contraseña mala; no cuenta como intento.
            await d.audit.record(
                replace(failed_ctx, actor_staff_id=user.id),
                "auth.login_failed",
                after={"reason": "locked" if locked else "inactive"},
            )
            return INVALID_CREDENTIALS
        if not ok:
            updated = _lock_state(user, now)
            await d.users.save(updated)
            await d.audit.record(
                replace(failed_ctx, actor_staff_id=user.id),
                "auth.login_failed",
                after={"reason": "bad_password", "locked": updated.locked_until is not None},
            )
            return INVALID_CREDENTIALS

        if user.failed_attempts:
            await d.users.save(replace(user, failed_attempts=0, updated_at=now))
        if user.totp_enabled:
            token = d.security.issue("mfa", user.id, MFA_TTL)
            return LoginStep("mfa_required", token)
        token = d.security.issue("mfa_setup", user.id, MFA_SETUP_TTL)
        return LoginStep("mfa_setup_required", token, user.must_change_password)


class VerifyMfaUseCase:
    def __init__(self, deps: AuthDeps) -> None:
        self._d = deps

    async def execute(
        self, mfa_token: str, code: str, ctx: RequestContext
    ) -> TokenPair | AuthFailure:
        d = self._d
        now = d.clock()
        try:
            payload = d.security.decode(mfa_token, "mfa")
        except InvalidSessionToken:
            return AuthFailure(
                "invalid_session_token", "La verificación venció; iniciá sesión de nuevo."
            )
        user = await d.users.get_by_id(UUID(str(payload["sub"])))
        if (
            user is None
            or not user.is_active
            or not user.totp_enabled
            or user.totp_secret_encrypted is None
            or (user.locked_until is not None and user.locked_until > now)
        ):
            return INVALID_CREDENTIALS
        secret = d.security.decrypt(user.totp_secret_encrypted)
        step = verify_totp(secret, code, now, user.totp_last_step)
        if step is None:
            updated = _lock_state(user, now)
            await d.users.save(updated)
            await d.audit.record(
                replace(ctx, actor_staff_id=user.id, actor_email=user.email),
                "auth.mfa_failed",
                after={"locked": updated.locked_until is not None},
            )
            return INVALID_MFA
        user = replace(
            user, totp_last_step=step, failed_attempts=0, last_login_at=now, updated_at=now
        )
        await d.users.save(user)
        pair = await _open_session(d, user, ctx)
        await d.audit.record(
            replace(ctx, actor_staff_id=user.id, actor_email=user.email), "auth.login"
        )
        return pair


class BeginMfaSetupUseCase:
    def __init__(self, deps: AuthDeps) -> None:
        self._d = deps

    async def execute(self, setup_token: str) -> MfaSetup:
        d = self._d
        payload = d.security.decode(setup_token, "mfa_setup")
        user = await d.users.get_by_id(UUID(str(payload["sub"])))
        if user is None or not user.is_active or user.totp_enabled:
            raise InvalidSessionToken("Token inválido.")
        secret = generate_totp_secret()
        # Queda pendiente (cifrado, sin `totp_enabled_at`) hasta que se confirme un código.
        await d.users.save(
            replace(user, totp_secret_encrypted=d.security.encrypt(secret), updated_at=d.clock())
        )
        return MfaSetup(secret=secret, otpauth_uri=otpauth_uri(secret, user.email))


class ConfirmMfaSetupUseCase:
    def __init__(self, deps: AuthDeps) -> None:
        self._d = deps

    async def execute(
        self, setup_token: str, code: str, new_password: str | None, ctx: RequestContext
    ) -> TokenPair | AuthFailure:
        d = self._d
        now = d.clock()
        try:
            payload = d.security.decode(setup_token, "mfa_setup")
        except InvalidSessionToken:
            return AuthFailure(
                "invalid_session_token", "La configuración venció; iniciá sesión de nuevo."
            )
        user = await d.users.get_by_id(UUID(str(payload["sub"])))
        if (
            user is None
            or not user.is_active
            or user.totp_enabled
            or user.totp_secret_encrypted is None
        ):
            return AuthFailure("invalid_session_token", "Token inválido.")

        password_hash = user.password_hash
        if user.must_change_password:
            if not new_password:
                return AuthFailure(
                    "weak_password", "Elegí una contraseña nueva para terminar la configuración."
                )
            try:
                validate_password_policy(new_password, email=user.email)
            except WeakPassword as exc:
                return AuthFailure("weak_password", str(exc))
            password_hash = await d.security.hash_password(new_password)

        secret = d.security.decrypt(user.totp_secret_encrypted)
        step = verify_totp(secret, code, now, user.totp_last_step)
        if step is None:
            updated = _lock_state(user, now)
            await d.users.save(updated)
            await d.audit.record(
                replace(ctx, actor_staff_id=user.id, actor_email=user.email),
                "auth.mfa_setup_failed",
            )
            return INVALID_MFA
        user = replace(
            user,
            password_hash=password_hash,
            must_change_password=False,
            totp_enabled_at=now,
            totp_last_step=step,
            failed_attempts=0,
            last_login_at=now,
            updated_at=now,
        )
        await d.users.save(user)
        pair = await _open_session(d, user, ctx)
        ctx_user = replace(ctx, actor_staff_id=user.id, actor_email=user.email)
        await d.audit.record(
            ctx_user, "auth.mfa_enabled", target_type="staff", target_id=str(user.id)
        )
        await d.audit.record(ctx_user, "auth.login")
        return pair


class RefreshSessionUseCase:
    """Rota el refresh token. Reutilizar uno ya rotado revoca **todas** las sesiones."""

    def __init__(self, deps: AuthDeps) -> None:
        self._d = deps

    async def execute(self, refresh_token: str, ctx: RequestContext) -> TokenPair | AuthFailure:
        d = self._d
        now = d.clock()
        invalid = AuthFailure("invalid_session_token", "La sesión venció; iniciá sesión de nuevo.")
        try:
            payload = d.security.decode(refresh_token, "refresh")
            jti = UUID(str(payload["jti"]))
        except (InvalidSessionToken, KeyError, ValueError):
            return invalid
        session = await d.sessions.get(jti)
        if session is None:
            return invalid
        user = await d.users.get_by_id(session.staff_user_id)
        if user is None:
            return invalid
        if session.revoked_at is not None:
            # Reutilización: alguien tiene un token que ya se rotó. Se corta todo.
            await d.sessions.revoke_all_of_user(user.id, now)
            await d.audit.record(
                replace(ctx, actor_staff_id=user.id, actor_email=user.email),
                "auth.refresh_reuse_detected",
            )
            return invalid
        if session.expires_at <= now or not user.is_active:
            return invalid
        await d.sessions.revoke(jti, now)
        return await _open_session(d, user, ctx, expires_at=session.expires_at)


class LogoutUseCase:
    def __init__(self, deps: AuthDeps) -> None:
        self._d = deps

    async def execute(self, refresh_token: str | None, ctx: RequestContext) -> None:
        if not refresh_token:
            return
        d = self._d
        try:
            payload = d.security.decode(refresh_token, "refresh")
            jti = UUID(str(payload["jti"]))
        except (InvalidSessionToken, KeyError, ValueError):
            return
        session = await d.sessions.get(jti)
        if session is None:
            return
        await d.sessions.revoke(jti, d.clock())
        user = await d.users.get_by_id(session.staff_user_id)
        await d.audit.record(
            replace(
                ctx,
                actor_staff_id=session.staff_user_id,
                actor_email=user.email if user else None,
            ),
            "auth.logout",
        )


class AuthenticateStaffUseCase:
    """Valida un access token y devuelve quién es (sesión vigente y usuario activo)."""

    def __init__(self, deps: AuthDeps) -> None:
        self._d = deps

    async def execute(self, access_token: str) -> Principal:
        d = self._d
        payload = d.security.decode(access_token, "access")
        try:
            jti = UUID(str(payload["jti"]))
            user_id = UUID(str(payload["sub"]))
        except (KeyError, ValueError) as exc:
            raise InvalidSessionToken("Token inválido.") from exc
        session = await d.sessions.get(jti)
        now = d.clock()
        if (
            session is None
            or session.staff_user_id != user_id
            or session.revoked_at is not None
            or session.expires_at <= now
        ):
            raise InvalidSessionToken("La sesión no está vigente.")
        user = await d.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidSessionToken("La sesión no está vigente.")
        return Principal(user=user, session=session)


@dataclass(frozen=True)
class CreatedStaff:
    user: StaffUser
    temporary_password: str


class CreateStaffUseCase:
    """Alta de un usuario del staff con contraseña temporal (se imprime una sola vez)."""

    def __init__(self, deps: AuthDeps) -> None:
        self._d = deps

    async def execute(
        self, *, email: str, full_name: str, role: Role, ctx: RequestContext
    ) -> CreatedStaff:
        d = self._d
        clean = normalize_email(email)
        if "@" not in clean or len(clean) > EMAIL_MAX_LENGTH or " " in clean:
            raise InvalidStaffData("El correo no es válido.")
        name = full_name.strip()
        if not name or len(name) > 200:
            raise InvalidStaffData("El nombre es obligatorio y admite hasta 200 caracteres.")
        if await d.users.get_by_email(clean) is not None:
            raise StaffEmailAlreadyExists(f"Ya existe un usuario con el correo {clean}.")
        temporary = generate_temporary_password()
        now = d.clock()
        user = StaffUser(
            id=uuid4(),
            email=clean,
            full_name=name,
            password_hash=await d.security.hash_password(temporary),
            role=role,
            is_active=True,
            must_change_password=True,
            failed_attempts=0,
            created_at=now,
            updated_at=now,
        )
        await d.users.add(user)
        await d.audit.record(
            ctx,
            "staff.create",
            target_type="staff",
            target_id=str(user.id),
            after={"email": clean, "role": role.value},
        )
        return CreatedStaff(user=user, temporary_password=temporary)


__all__ = [
    "AuthDeps",
    "AuthFailure",
    "AuthenticateStaffUseCase",
    "BeginMfaSetupUseCase",
    "ConfirmMfaSetupUseCase",
    "CreateStaffUseCase",
    "CreatedStaff",
    "LoginStep",
    "LoginUseCase",
    "LogoutUseCase",
    "MfaSetup",
    "Principal",
    "RefreshSessionUseCase",
    "TokenPair",
    "VerifyMfaUseCase",
    "normalize_email",
]
