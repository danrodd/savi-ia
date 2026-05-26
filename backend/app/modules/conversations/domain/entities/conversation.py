from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class Conversation:
    id: UUID = field(default_factory=uuid4)
    user_id: UUID | None = None
    title: str = "Nueva conversación"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    deleted_at: datetime | None = None

    def rename(self, new_title: str) -> None:
        new_title = new_title.strip()
        if not new_title:
            raise ValueError("El título no puede estar vacío")
        if len(new_title) > 200:
            raise ValueError("El título no puede superar 200 caracteres")
        self.title = new_title
        self.updated_at = datetime.utcnow()

    def soft_delete(self) -> None:
        self.deleted_at = datetime.utcnow()

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
