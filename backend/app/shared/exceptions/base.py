class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


class ValidationError(DomainError):
    pass


class RateLimitExceededError(DomainError):
    """Demasiados pedidos para esta clave. El handler global la mapea a 429
    con `Retry-After`, para que el cliente sepa cuándo reintentar en lugar de
    machacar."""

    def __init__(self, *, retry_after_seconds: int, detail: str | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        self.detail = detail or (
            f"Demasiados intentos. Probá de nuevo en {retry_after_seconds} segundos."
        )
        super().__init__(self.detail)


class ConversationBusyError(DomainError):
    """Ya hay un turno en curso en esa conversación.

    Se mapea a 409 con `errorCode: conversation_busy`: el pedido es válido,
    lo que falla es el momento. Dos turnos a la vez sobre la misma
    conversación dejan ramas cruzadas."""

    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        super().__init__("Ya hay una respuesta en curso en esta conversación.")


class ForbiddenError(DomainError):
    """El usuario está autenticado pero no tiene permiso para esta acción.

    El handler global la mapea a HTTP 403. Distinta de
    `ModuleAccessDeniedError` (que es específica de módulos del ERP):
    esta es genérica para reglas de autorización como "solo admins".
    """

    pass
