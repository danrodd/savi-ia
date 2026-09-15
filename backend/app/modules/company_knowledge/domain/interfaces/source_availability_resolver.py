from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.modules.company_knowledge.domain.services.document_access_policy import (
    DocumentAccessContext,
)


@dataclass(frozen=True, slots=True)
class SourceAvailability:
    available: bool
    reason: str | None = None


class SourceAvailabilityResolver(ABC):
    """Resuelve si una fuente citada sigue disponible para quien consulta."""

    @abstractmethod
    async def resolve(
        self, document_ids: Sequence[UUID], ctx: DocumentAccessContext
    ) -> dict[UUID, SourceAvailability]: ...
