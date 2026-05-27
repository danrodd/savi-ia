from app.shared.exceptions.base import ValidationError


class EmptyMessageError(ValidationError):
    def __init__(self) -> None:
        super().__init__("El mensaje no puede estar vacío")


class NothingToEditError(ValidationError):
    def __init__(self) -> None:
        super().__init__(
            "No hay un mensaje del usuario que se pueda editar en esta conversación"
        )


class NoAssistantToRegenerateError(ValidationError):
    def __init__(self) -> None:
        super().__init__(
            "No hay una respuesta del asistente que se pueda regenerar; "
            "envía primero un mensaje"
        )
