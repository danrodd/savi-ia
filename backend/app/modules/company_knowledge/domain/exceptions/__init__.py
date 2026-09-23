from app.modules.company_knowledge.domain.exceptions.exceptions import (
    AiReadingError,
    CompanyDocumentConflictError,
    CompanyDocumentFileTooLargeError,
    CompanyDocumentIndexLimitReachedError,
    CompanyDocumentInvalidError,
    CompanyDocumentNotFoundError,
    DocumentExtractionError,
    DuplicateCompanyDocumentError,
    EmbedderUnavailableError,
    UnsupportedCompanyDocumentMediaTypeError,
)

__all__ = [
    "AiReadingError",
    "CompanyDocumentConflictError",
    "CompanyDocumentFileTooLargeError",
    "CompanyDocumentIndexLimitReachedError",
    "CompanyDocumentInvalidError",
    "CompanyDocumentNotFoundError",
    "DocumentExtractionError",
    "DuplicateCompanyDocumentError",
    "EmbedderUnavailableError",
    "UnsupportedCompanyDocumentMediaTypeError",
]
