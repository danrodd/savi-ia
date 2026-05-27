from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.conversations.domain.entities import Message


class AssistantMessageWriter(ABC):
    """Puerto de salida para persistir el mensaje del asistente al cierre
    de un turno, con su metadata (tool_invocations, finish_reason, usage,
    cost).

    Las implementaciones deben usar una **sesión de base de datos
    independiente** de la del request HTTP. Esto permite que la persistencia
    sobreviva a la cancelación del cliente (`asyncio.CancelledError`) sin
    perder el contenido parcial generado.

    Si `supersedes_id` se pasa, además de insertar el nuevo mensaje hace
    `UPDATE messages SET superseded_by_id = nuevo WHERE id = supersedes_id`
    en la misma transacción. Esto cierra el ciclo de un `regenerate` o
    `edit_last`: el assistant viejo había quedado con
    `superseded_at=now()` pero `superseded_by_id=NULL` (porque cuando lo
    superseded aún no existía el nuevo).
    """

    @abstractmethod
    async def write(
        self,
        message: Message,
        *,
        supersedes_id: UUID | None = None,
    ) -> None: ...
