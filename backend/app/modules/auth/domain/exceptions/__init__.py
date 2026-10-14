from app.modules.auth.domain.exceptions.exceptions import (
    AuthError,
    DatabaseDisabledError,
    DatabaseUnreachableError,
    InvalidCredentialsError,
    InvalidTokenError,
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
    "InvalidTokenError",
    "ModuleAccessDeniedError",
    "RefreshTokenRevokedError",
    "UnknownDatabaseError",
    "UserDisabledError",
]
