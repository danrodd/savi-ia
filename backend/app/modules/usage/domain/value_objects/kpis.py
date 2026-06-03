from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ConversationStats:
    """Estadística de consumo a nivel conversación.

    Incluye percentiles porque el PROMEDIO solo no alcanza para fijar
    tarifa: lo distorsiona el usuario pesado. El p95 es el número con el
    que se cubre el riesgo (el 95% de las conversaciones cuesta menos que
    eso). Todo en USD (display analytics → float, no Decimal de ledger).
    """

    count: int
    avg_cost_usd: float
    p50_cost_usd: float
    p90_cost_usd: float
    p95_cost_usd: float
    max_cost_usd: float
    avg_tokens: float
    avg_turns: float


@dataclass(frozen=True, slots=True)
class UserStats:
    """Estadística de consumo a nivel usuario (excluye conversaciones
    legadas sin `user_id`, que no son un usuario facturable real)."""

    active_count: int
    avg_cost_usd: float
    avg_conversations: float


@dataclass(frozen=True, slots=True)
class ConversationUsage:
    """Fila de consumo de una conversación — para tabla y export CSV."""

    conversation_id: UUID
    user_id: int | None
    title: str
    turns: int
    total_tokens: int
    cost_usd: float
    last_activity: datetime
