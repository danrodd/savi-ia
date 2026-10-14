"""Excepciones del dominio de auth.

Los handlers HTTP globales las mapean a status codes:
- AuthError / InvalidCredentialsError → 401
- UnknownDatabaseError → 401 con `errorCode: unknown_database`
- DatabaseDisabledError → 401 con `errorCode: database_disabled`
- DatabaseUnreachableError → 503 con `errorCode: database_unreachable`
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
    def __init__(self, message: str = "Usuario o contraseña inválidos") -> None:
        super().__init__(message)


class UnknownDatabaseError(InvalidCredentialsError):
    """El código de cliente de `USUARIO@CODIGO` no corresponde a ninguna base
    usable.

    Es un `InvalidCredentialsError` a propósito: sigue siendo un login
    fallido (cuenta para el límite de intentos y comparte el piso de
    duración), solo que la respuesta le dice a la persona qué revisar. Habla
    únicamente de la base: nunca revela si el usuario existe.
    """

    def __init__(self) -> None:
        super().__init__("No encontramos ese cliente. Revisá el código después de la @.")


class DatabaseDisabledError(InvalidCredentialsError):
    """El cliente de `USUARIO@CODIGO` existe pero está desactivado en SAVI.

    Es un `InvalidCredentialsError` por la misma razón que
    `UnknownDatabaseError`: sigue siendo un login fallido (cuenta para el
    límite de intentos y comparte el piso de duración). Habla únicamente de
    la base: nunca revela si el usuario existe.
    """

    def __init__(self) -> None:
        super().__init__("Ese cliente está desactivado en SAVI. Avisale a tu administrador.")


class DatabaseUnreachableError(AuthError):
    """El cliente existe y está activo, pero no se pudo conectar con su ERP
    (red, credenciales de conexión, timeout o base sin el esquema esperado).

    NO es un `InvalidCredentialsError`: nadie adivinó nada, así que no suma
    al límite de intentos fallidos. Tampoco llegó a comparar contraseñas, de
    modo que no revela nada sobre el usuario.
    """

    def __init__(self) -> None:
        super().__init__(
            "No pudimos conectar con la base de ese cliente. "
            "Probá de nuevo en unos minutos o avisale a tu administrador."
        )


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
