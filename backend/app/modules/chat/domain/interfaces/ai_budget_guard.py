"""Puerto: ¿esta persona puede usar IA ahora? Se consulta antes de abrir el SSE."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.chat.domain.interfaces.active_provider import ActiveProvider


class AiBudgetGuard(ABC):
    @abstractmethod
    async def check(
        self, *, user_id: int, erp_database_id: UUID, provider: ActiveProvider
    ) -> None:
        """Levanta `AiAccessDeniedError` si la política de SEO Group no permite el turno."""
