from app.shared.exceptions.base import ValidationError


class EmptyMessageError(ValidationError):
    def __init__(self) -> None:
        super().__init__("El mensaje no puede estar vacío")
