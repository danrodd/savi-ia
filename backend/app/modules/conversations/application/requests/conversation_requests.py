from uuid import UUID

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    user_id: UUID | None = Field(default=None)


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
