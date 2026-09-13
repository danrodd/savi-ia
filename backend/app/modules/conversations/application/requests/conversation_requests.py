from uuid import UUID

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    # `user_id` no se acepta más desde el body — se toma del usuario
    # autenticado en el endpoint. Mantener el campo en el request abriría
    # un agujero de impersonation.
    #
    # Base del ERP contra la que se va a consultar. Ausente = la base de
    # identidad del usuario. El endpoint valida que el usuario tenga
    # acceso a ella (D3): no se acepta a ciegas. Inmutable una vez creada
    # la conversación.
    erp_database_id: UUID | None = Field(default=None)


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
