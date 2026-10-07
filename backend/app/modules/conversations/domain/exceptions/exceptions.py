from uuid import UUID

from app.shared.exceptions.base import DomainError, NotFoundError, ValidationError


class ConversationNotFoundError(NotFoundError):
    def __init__(self, conversation_id: UUID):
        super().__init__(f"Conversación {conversation_id} no encontrada")
        self.conversation_id = conversation_id


class ChatAttachmentNotFoundError(NotFoundError):
    """No existe o no es del usuario: no se distinguen, para no confirmar ids."""

    def __init__(self) -> None:
        super().__init__("Imagen no encontrada.")


class ChatAttachmentTooLargeError(DomainError):
    """Se mapea a 413 (ver `register_exception_handlers`)."""

    def __init__(self, limit_mb: int) -> None:
        super().__init__(f"La imagen supera el límite de {limit_mb} MB.")
        self.limit_mb = limit_mb


class InvalidChatAttachmentError(ValidationError):
    """El archivo no es una imagen admitida (422)."""


class ChatAttachmentUnavailableError(ValidationError):
    """Un adjunto del mensaje no existe, no es del usuario o ya se usó (422)."""
