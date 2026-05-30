from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    # `user_id` no se acepta más desde el body — se toma del usuario
    # autenticado en el endpoint. Mantener el campo en el request abriría
    # un agujero de impersonation.


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
