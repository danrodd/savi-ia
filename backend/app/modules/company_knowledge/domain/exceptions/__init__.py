from app.modules.company_knowledge.domain.exceptions.exceptions import (
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
