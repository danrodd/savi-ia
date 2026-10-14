from uuid import UUID

from app.shared.exceptions.base import NotFoundError, ValidationError


class FeedbackTargetNotFoundError(NotFoundError):
    """El mensaje no existe o no es de una conversación del usuario.

    No se distinguen: no se confirma la existencia de mensajes ajenos.
    """

    def __init__(self, message_id: UUID):
        super().__init__(f"Mensaje {message_id} no encontrado")
        self.message_id = message_id


class FeedbackNotAllowedError(ValidationError):
    """Se puede calificar solo una respuesta vigente del asistente (422)."""
