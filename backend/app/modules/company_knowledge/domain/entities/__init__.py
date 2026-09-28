from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
    DocumentChunk,
)
from app.modules.company_knowledge.domain.entities.document_access_view import (
    DocumentAccessView,
)
from app.modules.company_knowledge.domain.entities.page_reading import (
    AiPageContent,
    AiReadRecord,
    AiReadResult,
    AiReadUsage,
    KnowledgeSettings,
    PageMetrics,
    PdfAnalysis,
    ReadPage,
)
from app.modules.company_knowledge.domain.entities.processing import (
    ChunkDraft,
    ExtractedText,
    PendingChunk,
)
from app.modules.company_knowledge.domain.entities.web_source import (
    DiscoveredUrl,
    Discovery,
    ExtractedPage,
    FetchResult,
    WebPage,
    WebSource,
)

__all__ = [
    "AiPageContent",
    "AiReadRecord",
    "AiReadResult",
    "AiReadUsage",
    "KnowledgeSettings",
    "PageMetrics",
    "PdfAnalysis",
    "ReadPage",
    "ChunkDraft",
    "CompanyDocument",
    "DocumentAccessView",
    "DocumentChunk",
    "ExtractedText",
    "PendingChunk",
    "DiscoveredUrl",
    "Discovery",
    "ExtractedPage",
    "FetchResult",
    "WebPage",
    "WebSource",
]
