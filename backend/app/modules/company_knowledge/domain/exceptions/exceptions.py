from app.modules.company_knowledge.domain.value_objects.reading import AiReadErrorCode
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatusCode,
)
from app.shared.exceptions.base import DomainError, NotFoundError, ValidationError


class CompanyDocumentNotFoundError(NotFoundError):
    def __init__(self, document_id: str) -> None:
        super().__init__(f"No existe el documento {document_id}.")


class DuplicateCompanyDocumentError(DomainError):
    """Un archivo idéntico ya existe (mismo `sha256`, no eliminado)."""

    def __init__(self, existing_document_id: str, existing_title: str) -> None:
        super().__init__(f"Ya existe un documento idéntico: {existing_title}.")
        self.existing_document_id = existing_document_id
        self.existing_title = existing_title


class CompanyDocumentFileTooLargeError(DomainError):
    def __init__(self, limit_mb: int) -> None:
        super().__init__(f"El archivo supera el límite de {limit_mb} MB.")
        self.limit_mb = limit_mb


class UnsupportedCompanyDocumentMediaTypeError(DomainError):
    def __init__(self) -> None:
        super().__init__("Tipo de archivo no soportado. Se aceptan PDF, TXT y Markdown.")


class CompanyDocumentIndexLimitReachedError(DomainError):
    def __init__(self, limit: int) -> None:
        super().__init__(
            f"La instalación alcanzó el límite de {limit} fragmentos. "
            "Eliminá documentos para liberar espacio."
        )
        self.limit = limit


class CompanyDocumentConflictError(DomainError):
    """El documento está en un estado que impide la operación solicitada."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class CompanyDocumentInvalidError(ValidationError):
    pass


class DocumentExtractionError(DomainError):
    """Falla de extracción con un `status_code` estable para el documento."""

    def __init__(self, status_code: DocumentStatusCode, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code


class EmbedderUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "El modelo de embeddings no está disponible; no se pueden procesar "
            "documentos en este momento."
        )


class AiReadingError(Exception):
    """El proveedor no pudo leer un tramo.

    No es un error de dominio que llegue a HTTP: lo maneja la lectura, que
    reintenta si `retryable` y, si no, usa el texto de `pypdf` para esas
    páginas. El mensaje nunca incluye contenido del documento.
    """

    def __init__(self, code: AiReadErrorCode, *, retryable: bool, detail: str = "") -> None:
        super().__init__(detail or code.value)
        self.code = code
        self.retryable = retryable
