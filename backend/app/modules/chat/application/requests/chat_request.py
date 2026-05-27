from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ChatAction(StrEnum):
    SEND = "send"
    EDIT_LAST = "edit_last"
    REGENERATE = "regenerate"


class ChatRequest(BaseModel):
    """Acción discriminada para el endpoint `POST /chat`.

    - `send` (default): envía un nuevo mensaje del usuario y stream-ea
      la respuesta. Requiere `message`.
    - `edit_last`: reemplaza el último mensaje del usuario activo por
      `message`, marca el viejo (y el assistant que le respondió, si
      existe) como `superseded` y regenera. Requiere `message`.
    - `regenerate`: regenera la última respuesta del asistente sin tocar
      el mensaje del usuario. NO requiere `message` (se ignora si llega).
    """

    conversation_id: UUID
    action: ChatAction = ChatAction.SEND
    message: str | None = Field(default=None, max_length=16000)

    @model_validator(mode="after")
    def _validate_message_required(self) -> Self:
        if self.action in (ChatAction.SEND, ChatAction.EDIT_LAST) and (
            self.message is None or not self.message.strip()
        ):
            raise ValueError(
                f"`message` es obligatorio cuando action='{self.action.value}'"
            )
        return self
