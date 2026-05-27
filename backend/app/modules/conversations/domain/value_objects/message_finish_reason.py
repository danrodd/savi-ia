from enum import StrEnum


class MessageFinishReason(StrEnum):
    """Por qué terminó el turno del asistente.

    - COMPLETE: el modelo cerró su respuesta y emitió ResultMessage.
    - INTERRUPTED: el cliente cortó el stream (botón stop, cerrar pestaña).
    - ERROR: el runner emitió ErrorEvent o el stream lanzó una excepción.
    - TRUNCATED: la respuesta superó max_response_chars y fue cortada.
    """

    COMPLETE = "complete"
    INTERRUPTED = "interrupted"
    ERROR = "error"
    TRUNCATED = "truncated"
