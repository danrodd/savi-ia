from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Conversation:
    id: UUID = field(default_factory=uuid4)
    user_id: UUID | None = None
    title: str = "Nueva conversación"
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    deleted_at: datetime | None = None

    def rename(self, new_title: str) -> None:
        new_title = new_title.strip()
        if not new_title:
            raise ValueError("El título no puede estar vacío")
        if len(new_title) > 200:
            raise ValueError("El título no puede superar 200 caracteres")
        self.title = new_title
        self.updated_at = _utc_now()

    def soft_delete(self) -> None:
        self.deleted_at = _utc_now()

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
