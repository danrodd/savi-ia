"""Excepciones del dominio de auth.

Los handlers HTTP globales las mapean a status codes:
- AuthError / InvalidCredentialsError → 401
- UserDisabledError → 403
- InvalidTokenError → 401
- RefreshTokenRevokedError → 401
"""


class AuthError(Exception):
    """Base de errores de auth — el handler global la mapea a 401."""

    def __init__(self, message: str = "No autenticado") -> None:
        super().__init__(message)
        self.message = message


class InvalidCredentialsError(AuthError):
    def __init__(self) -> None:
        super().__init__("Usuario o contraseña inválidos")


class InvalidTokenError(AuthError):
    def __init__(self, detail: str = "Token inválido") -> None:
        super().__init__(detail)


class UserDisabledError(AuthError):
    def __init__(self) -> None:
        super().__init__("El usuario está deshabilitado en el sistema")


class RefreshTokenRevokedError(AuthError):
    def __init__(self) -> None:
        super().__init__("La sesión expiró. Iniciá sesión nuevamente.")


class ModuleAccessDeniedError(Exception):
    """El usuario no tiene acceso al módulo requerido por el endpoint.

    El handler global la mapea a HTTP 403 con `errorCode:
    module_access_denied` — el frontend ese código lo usa como señal
    para recargar el bootstrap (su caché de módulos podría estar stale).
    """

    def __init__(self, required_module: str) -> None:
        super().__init__(f"Sin acceso al módulo {required_module}")
        self.required_module = required_module
