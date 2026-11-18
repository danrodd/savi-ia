"""Archivo generado por SAVI para una respuesta (exportación o documento)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.documents.domain.result_set import RETENTION


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class StoredFile:
    conversation_id: UUID
    filename: str
    media_type: str
    content: bytes
    has_personal_data: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utc_now)

    @property
    def size_bytes(self) -> int:
        return len(self.content)

    @property
    def expires_at(self) -> datetime:
        return self.created_at + RETENTION

    def summary(self) -> dict[str, object]:
        """Lo que viaja al chat y queda en el mensaje: sin el contenido."""
        return {
            "id": str(self.id),
            "filename": self.filename,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
        }
