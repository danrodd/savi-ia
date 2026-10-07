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
      la respuesta. Requiere `message` o `attachment_ids`.
    - `edit_last`: reemplaza el último mensaje del usuario activo por
      `message`, marca el viejo (y el assistant que le respondió, si
      existe) como `superseded` y regenera. Requiere `message` o
      `attachment_ids`. Las imágenes que se conservan se vuelven a listar en
      `attachment_ids`.
    - `regenerate`: regenera la última respuesta del asistente sin tocar
      el mensaje del usuario (ni sus imágenes). NO requiere `message` (se
      ignora si llega, igual que `attachment_ids`).

    `attachment_ids`: imágenes subidas antes con `POST /chat/attachments`. El
    máximo por mensaje (`CHAT_IMAGES_PER_MESSAGE`) y la pertenencia de cada
    imagen se validan en el caso de uso, antes de abrir el stream.
    """

    conversation_id: UUID
    action: ChatAction = ChatAction.SEND
    message: str | None = Field(default=None, max_length=16000)
    attachment_ids: list[UUID] = Field(default_factory=list[UUID])

    @model_validator(mode="after")
    def _validate_message_required(self) -> Self:
        # Repetir un id no suma una imagen: se descartan los duplicados
        # conservando el orden.
        self.attachment_ids = list(dict.fromkeys(self.attachment_ids))
        has_text = self.message is not None and bool(self.message.strip())
        if (
            self.action in (ChatAction.SEND, ChatAction.EDIT_LAST)
            and not has_text
            and not self.attachment_ids
        ):
            raise ValueError(
                f"`message` o `attachment_ids` es obligatorio cuando action='{self.action.value}'"
            )
        return self
