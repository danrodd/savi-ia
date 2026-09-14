from abc import ABC, abstractmethod


class TitleGenerator(ABC):
    @abstractmethod
    async def generate(self, user_msg: str, assistant_msg: str = "") -> str | None:
        """Título corto para la conversación, o `None` si no se pudo generar."""
