from abc import ABC, abstractmethod
from uuid import UUID


class ConversationTitleUpdater(ABC):
    """Puerto para los autotítulos del chat.

    Las implementaciones combinan dos responsabilidades:
    - **Generar** el título llamando a un modelo LLM ligero (Haiku).
    - **Persistirlo** en la conversación respetando el flag `title_locked`
      (si el usuario renombró manualmente, no lo sobrescribimos).

    Deben usar una **sesión de BD independiente** del request, igual que
    `AssistantMessageWriter`, porque se invocan como `asyncio.create_task`
    desde el stream del chat.
    """

    @abstractmethod
    async def update_from_user(
        self,
        conversation_id: UUID,
        user_msg: str,
    ) -> str | None:
        """Fase 1: título provisional al iniciar el primer turno.

        Devuelve el título aplicado, o `None` si fue bloqueado o falló."""

    @abstractmethod
    async def update_from_turn(
        self,
        conversation_id: UUID,
        user_msg: str,
        assistant_msg: str,
    ) -> str | None:
        """Fase 2: título refinado con la respuesta del asistente a la vista.

        Devuelve el título aplicado, o `None` si fue bloqueado o falló."""
