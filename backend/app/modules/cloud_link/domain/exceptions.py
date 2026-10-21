from app.shared.exceptions.base import DomainError, ValidationError


class CloudApiError(DomainError):
    """Cloud no aceptó el pedido, o no se pudo hablar con Cloud.

    `status_code=None` es un fallo de transporte (sin conexión, DNS, TLS,
    timeout). `error_code` nunca lleva mensajes libres de Cloud: es un código
    corto, así que se puede guardar y mostrar sin riesgo de filtrar datos.
    """

    def __init__(
        self,
        error_code: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds

    @property
    def is_transient(self) -> bool:
        """Red, `5xx` y `429`: se reintenta el mismo pedido con backoff."""
        return self.status_code is None or self.status_code >= 500 or self.status_code == 429

    @property
    def is_revoked(self) -> bool:
        return self.status_code == 401 and self.error_code == "instance_revoked"

    @property
    def is_unauthorized(self) -> bool:
        return self.status_code == 401 and not self.is_revoked


class AlreadyLinkedError(ValidationError):
    def __init__(self) -> None:
        super().__init__("Esta instalación ya está vinculada con SAVI Cloud. Desvincúlela primero.")


class NotLinkedError(ValidationError):
    def __init__(self) -> None:
        super().__init__("Esta instalación no está vinculada con SAVI Cloud.")


class CloudNotConfiguredError(ValidationError):
    def __init__(self) -> None:
        super().__init__(
            "SAVI Cloud no está configurado en esta instalación (falta SAVI_CLOUD_URL)."
        )


class InsecureCloudUrlError(ValidationError):
    def __init__(self) -> None:
        super().__init__(
            "La dirección de SAVI Cloud debe usar https. Solo en desarrollo se acepta http."
        )
