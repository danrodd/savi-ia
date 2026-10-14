from app.modules.auth.domain.exceptions.exceptions import (
    AuthError,
    DatabaseDisabledError,
    DatabaseUnreachableError,
    InvalidCredentialsError,
    InvalidMfaCodeError,
    InvalidTokenError,
    MfaUnavailableError,
    ModuleAccessDeniedError,
    RefreshTokenRevokedError,
    UnknownDatabaseError,
    UserDisabledError,
)

__all__ = [
    "AuthError",
    "DatabaseDisabledError",
    "DatabaseUnreachableError",
    "InvalidCredentialsError",
    "InvalidMfaCodeError",
    "InvalidTokenError",
    "MfaUnavailableError",
    "ModuleAccessDeniedError",
    "RefreshTokenRevokedError",
    "UnknownDatabaseError",
    "UserDisabledError",
]
