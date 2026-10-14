from app.shared.exceptions.base import DomainError, ValidationError


class LlmProviderUnavailableError(DomainError):
    """No hay proveedor de IA activo, o el activo no se puede usar
    (credencial ilegible, sin modelos).

    Se mapea a **409** con `errorCode: "llm_provider_unavailable"` y se
    levanta ANTES de abrir el SSE: adentro del stream ya no se puede
    cambiar el status code.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class AiAccessDeniedError(DomainError):
    """La política de IA de SEO Group no permite este turno.

    Se mapea a **403** con un `errorCode` estable (`ai_provider_not_allowed`,
    `ai_budget_exceeded` o `ai_price_missing`) y se levanta ANTES de abrir el SSE.
    """

    def __init__(self, code: str, reason: str) -> None:
        self.error_code = code
        self.reason = reason
        super().__init__(reason)


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


class TooManyChatImagesError(ValidationError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"Un mensaje admite hasta {limit} imágenes adjuntas.")
        self.limit = limit
