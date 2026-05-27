from abc import ABC, abstractmethod

from app.modules.conversations.domain.entities import Message


class AssistantMessageWriter(ABC):
    """Puerto de salida para persistir el mensaje del asistente al cierre
    de un turno, con su metadata (tool_invocations, finish_reason, usage,
    cost).

    Las implementaciones deben usar una **sesión de base de datos
    independiente** de la del request HTTP. Esto permite que la persistencia
    sobreviva a la cancelación del cliente (`asyncio.CancelledError`) sin
    perder el contenido parcial generado.
    """

    @abstractmethod
    async def write(self, message: Message) -> None: ...
